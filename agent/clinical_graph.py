"""Minimal LangGraph supervisor with two workers.

Graph:

    START → supervisor ──┬──→ intake_extractor ──→ supervisor (loops)
                         ├──→ evidence_retriever ──→ supervisor (loops)
                         └──→ END  (when supervisor decides the answer is ready)

The supervisor inspects accumulated state on every visit and decides the
next handoff. Workers do their job and return to the supervisor — they do
not decide what runs next, and they do not produce the final answer.

Run:
    python3 clinical_graph.py
"""

from __future__ import annotations

import json
import os
from typing import Annotated, Optional, TypedDict

from anthropic import Anthropic
from langgraph.graph import END, START, StateGraph

# Load .env so ANTHROPIC_API_KEY is available.
_env = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env):
    for _line in open(_env):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k, _v.strip().strip('"').strip("'"))

from document_extractor import extract_document
from evidence_retriever import index_guidelines, search_evidence

MODEL = "claude-sonnet-4-5"
_client = Anthropic()


# ── State ──────────────────────────────────────────────────────────────────

def _append(left: list, right: list) -> list:
    return (left or []) + (right or [])


class GraphState(TypedDict, total=False):
    """Shared state. `handoffs` is append-only so the trace is auditable."""
    query: str                             # The clinician question
    file_path: Optional[str]               # Document path, if one was attached
    doc_type: Optional[str]                # 'intake_form' or 'lab_pdf'
    extraction: Optional[dict]             # Result from intake_extractor
    evidence: Optional[list]               # Result from evidence_retriever
    final_answer: Optional[str]            # Filled when supervisor decides we're done
    handoffs: Annotated[list, _append]     # Audit trail of handoff decisions
    next: Optional[str]                    # Supervisor's next-step decision


# ── Supervisor ─────────────────────────────────────────────────────────────

_SUPERVISOR_SYSTEM = """You coordinate two clinical workers:

1. intake_extractor — extracts structured data from an attached patient
   document (intake form or lab PDF). Only useful when a `file_path` is
   present in state and `extraction` has not yet been filled.
2. evidence_retriever — searches an indexed clinical-guideline corpus and
   returns relevant snippets for a query. Useful when the answer depends on
   guideline-backed reasoning.

Decide the next step. Respond with strict JSON:
  {"next": "intake_extractor" | "evidence_retriever" | "finish",
   "answer": "<final answer if next == 'finish', else empty>",
   "reason": "<one sentence explaining the choice>"}

Rules:
- If a file is attached and not yet extracted, route to intake_extractor.
- If the query asks for guideline-backed reasoning and no evidence has been
  retrieved yet, route to evidence_retriever.
- Once you have all the information needed to answer the query, choose
  "finish" and write the answer in `answer` using the gathered context.
- Never call the same worker twice if its output is already in state.
"""


def _state_summary(state: GraphState) -> str:
    parts = [f"query: {state.get('query')!r}"]
    if state.get("file_path"):
        parts.append(f"file_path: {state['file_path']!r} (doc_type={state.get('doc_type')!r})")
    parts.append(f"extraction_done: {state.get('extraction') is not None}")
    parts.append(f"evidence_done: {state.get('evidence') is not None}")
    if state.get("extraction"):
        # Compact preview so the supervisor can reason about the content.
        parts.append(f"extraction_preview: {json.dumps(state['extraction'])[:600]}")
    if state.get("evidence"):
        snips = [e.get("text", "")[:160] for e in state["evidence"][:3]]
        parts.append(f"evidence_preview: {snips}")
    return "\n".join(parts)


def supervisor(state: GraphState) -> GraphState:
    """Inspect state, ask the model what to do next, log the handoff."""
    resp = _client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=_SUPERVISOR_SYSTEM,
        messages=[{"role": "user", "content": _state_summary(state)}],
    )
    raw = resp.content[0].text.strip()
    # Strip any accidental code fences before parsing.
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
    decision = json.loads(raw)

    update: GraphState = {
        "next": decision["next"],
        "handoffs": [{
            "from": "supervisor",
            "to": decision["next"],
            "reason": decision.get("reason", ""),
        }],
    }
    if decision["next"] == "finish":
        update["final_answer"] = decision.get("answer", "")
    return update


def _route_from_supervisor(state: GraphState) -> str:
    nxt = state.get("next")
    if nxt == "intake_extractor":
        return "intake_extractor"
    if nxt == "evidence_retriever":
        return "evidence_retriever"
    return END


# ── Workers ────────────────────────────────────────────────────────────────

def intake_extractor(state: GraphState) -> GraphState:
    """Extract structured fields from the attached document."""
    file_path = state.get("file_path")
    doc_type = state.get("doc_type") or "intake_form"
    if not file_path:
        return {
            "extraction": {"success": False, "error": "no file_path in state"},
            "handoffs": [{"from": "intake_extractor", "to": "supervisor", "reason": "no file"}],
        }
    result = extract_document(file_path, doc_type)
    return {
        "extraction": result,
        "handoffs": [{
            "from": "intake_extractor",
            "to": "supervisor",
            "reason": f"extracted {os.path.basename(file_path)} ({'ok' if result.get('success') else 'error'})",
        }],
    }


def evidence_retriever(state: GraphState) -> GraphState:
    """Search the guideline corpus for snippets relevant to the query."""
    query = state.get("query") or ""
    snippets = search_evidence(query, top_k=5)
    return {
        "evidence": snippets,
        "handoffs": [{
            "from": "evidence_retriever",
            "to": "supervisor",
            "reason": f"retrieved {len(snippets)} snippets",
        }],
    }


# ── Build & expose ─────────────────────────────────────────────────────────

def build_graph():
    g = StateGraph(GraphState)
    g.add_node("supervisor", supervisor)
    g.add_node("intake_extractor", intake_extractor)
    g.add_node("evidence_retriever", evidence_retriever)

    g.add_edge(START, "supervisor")
    g.add_conditional_edges(
        "supervisor",
        _route_from_supervisor,
        {"intake_extractor": "intake_extractor", "evidence_retriever": "evidence_retriever", END: END},
    )
    # Workers always hand control back to the supervisor.
    g.add_edge("intake_extractor", "supervisor")
    g.add_edge("evidence_retriever", "supervisor")
    return g.compile()


# Build once at import time. Index the guideline corpus on first use.
GRAPH = build_graph()
index_guidelines()


def run(query: str, file_path: str = "", doc_type: str = "") -> dict:
    """Convenience runner. Returns the terminal state."""
    initial: GraphState = {"query": query, "handoffs": []}
    if file_path:
        initial["file_path"] = file_path
        initial["doc_type"] = doc_type or "intake_form"
    return GRAPH.invoke(initial)


# ── Demo ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n=== Demo 1: query needing only evidence ===")
    out = run("What HbA1c target does the ADA recommend for adults with T2DM?")
    print("answer:", out.get("final_answer"))
    for h in out.get("handoffs", []):
        print(f"  {h['from']} → {h['to']} ({h['reason']})")

    print("\n=== Demo 2: query needing extraction then evidence ===")
    out = run(
        "Summarize this patient's lipid panel and tell me what the ACC/AHA guideline recommends.",
        file_path="sample_docs/lab-results/p01-chen-lipid-panel.pdf",
        doc_type="lab_pdf",
    )
    print("answer:", out.get("final_answer"))
    for h in out.get("handoffs", []):
        print(f"  {h['from']} → {h['to']} ({h['reason']})")
