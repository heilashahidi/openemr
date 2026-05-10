"""
Run the existing 58-case clinical-graph eval as a LangSmith experiment.

This is a thin shim around `eval_clinical_graph.py` — the rubric logic
lives there and stays the single source of truth for what "pass" means.
This module:

  1. Uploads the 58 cases to a LangSmith dataset (idempotent — only
     creates examples that don't already exist, so re-running won't
     duplicate rows).
  2. Defines a target function that runs each case's rubric `fn()`
     and surfaces the boolean pass/fail to LangSmith as an output.
  3. Defines `passed` and `category` evaluators so the LangSmith UI
     can sort, filter, and bucket results by rubric.

Why bother when CI already runs the same 58 cases?

  - LangSmith UI is much better for **interactive** drill-down: side-by-
    side compare across runs, sort by latency, filter by category,
    re-run a single failing case after a prompt tweak without spinning
    up the whole CI pipeline.
  - Every graph call inside the rubric also writes a trace tree to
    LangSmith, so a failing case has a clickable supervisor → worker
    breakdown right next to its pass/fail row.
  - `eval_clinical_graph.py` stays the PR-blocking gate (CI exit code).
    LangSmith Evals is the iteration loop on top of that gate.

Run with:
  cd agent && python langsmith_eval.py

Requires `LANGCHAIN_API_KEY` (project: clinical-copilot) plus the same
`OPENEMR_*` + `ANTHROPIC_API_KEY` env the local eval needs (the rubric
fn's call into the running agent for chart_lookup, retrieval, etc.).
"""

from __future__ import annotations

import os
import sys
from typing import Callable

from dotenv import load_dotenv

from eval_clinical_graph import ALL_CASES, Case

load_dotenv()

DATASET_NAME = "clinical-copilot-58"
DATASET_DESCRIPTION = (
    "58 boolean-rubric cases covering schema validation, citation "
    "presence, factual consistency, safe refusal, no-PHI logging, and "
    "evidence separation. Mirrors agent/eval_clinical_graph.py."
)
EXPERIMENT_PREFIX = "clinical-copilot"


def _require_langsmith_key() -> None:
    if not (os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY")):
        print(
            "ERROR: LANGCHAIN_API_KEY (or LANGSMITH_API_KEY) is not set.\n"
            "Add it to agent/.env and re-run.",
            file=sys.stderr,
        )
        sys.exit(2)


def upload_dataset(client) -> str:
    """Create the dataset if missing; insert any cases not already present.

    Idempotent: re-running this never duplicates examples or overwrites
    existing ones — case ids are the dedup key via the example metadata.
    """
    try:
        ds = client.read_dataset(dataset_name=DATASET_NAME)
        print(f"  dataset exists: {DATASET_NAME} (id={ds.id})")
    except Exception:
        ds = client.create_dataset(
            dataset_name=DATASET_NAME,
            description=DATASET_DESCRIPTION,
        )
        print(f"  dataset created: {DATASET_NAME} (id={ds.id})")

    existing_ids: set[str] = set()
    for ex in client.list_examples(dataset_id=ds.id):
        cid = (ex.metadata or {}).get("case_id")
        if cid:
            existing_ids.add(cid)

    new_examples = []
    for case in ALL_CASES:
        if case.id in existing_ids:
            continue
        new_examples.append({
            "inputs": {
                "case_id": case.id,
                "category": case.category,
                "description": case.description,
            },
            "outputs": {"expected_pass": True},
            "metadata": {"case_id": case.id, "category": case.category},
        })

    if new_examples:
        client.create_examples(dataset_id=ds.id, examples=new_examples)
        print(f"  added {len(new_examples)} new example(s)")
    else:
        print("  dataset is up to date — no new examples")

    return DATASET_NAME


def make_target(cases: list[Case]) -> Callable[[dict], dict]:
    """Build a closure that maps an example's `case_id` back to the
    rubric `fn` and runs it.

    The target's return dict shape:
        {"passed": bool, "reason": str, "category": str}

    Wrapped in a try/except so a Python error inside a single rubric
    doesn't blow up the whole experiment — it just records the case
    as failed with the exception text.
    """
    by_id = {c.id: c for c in cases}

    def target(inputs: dict) -> dict:
        case = by_id.get(inputs.get("case_id"))
        if case is None:
            return {
                "passed": False,
                "reason": f"case not found: {inputs.get('case_id')}",
                "category": inputs.get("category", ""),
            }
        try:
            passed, reason = case.fn()
        except Exception as e:  # noqa: BLE001 — we want the whole class
            return {
                "passed": False,
                "reason": f"exception: {type(e).__name__}: {e}",
                "category": case.category,
            }
        return {
            "passed": bool(passed),
            "reason": str(reason),
            "category": case.category,
        }

    return target


# Evaluators run AFTER the target. They receive the full Run + Example
# and return scoring metadata that LangSmith renders as columns. Score
# = 1 → pass (green), score = 0 → fail (red).

def passed_evaluator(run, example) -> dict:
    output = run.outputs or {}
    return {
        "key": "passed",
        "score": 1 if output.get("passed") else 0,
        "comment": str(output.get("reason", ""))[:300],
    }


def category_evaluator(run, example) -> dict:
    """Per-category score. Lets LangSmith group/aggregate by rubric in
    the experiment view (e.g. you can see schema_valid pass-rate
    independent of safe_refusal pass-rate)."""
    output = run.outputs or {}
    return {
        "key": output.get("category", "unknown"),
        "score": 1 if output.get("passed") else 0,
    }


def main() -> None:
    _require_langsmith_key()

    # Imported here so the script doesn't fail on systems where
    # langsmith isn't installed unless someone actually runs it.
    from langsmith import Client
    from langsmith.evaluation import evaluate

    client = Client()
    print(f"loaded {len(ALL_CASES)} cases from eval_clinical_graph.ALL_CASES")

    dataset_name = upload_dataset(client)

    print("running experiment (each case runs the local rubric fn — "
          "expect ~10 min for the full 58)...")
    results = evaluate(
        make_target(ALL_CASES),
        data=dataset_name,
        evaluators=[passed_evaluator, category_evaluator],
        experiment_prefix=EXPERIMENT_PREFIX,
        max_concurrency=4,
    )

    # `evaluate()` returns an iterable; list() forces it to drain so all
    # results are uploaded before the script exits. The print at the end
    # just shows the experiment URL — the real signal is in LangSmith.
    list(results)
    print("experiment complete — view at https://smith.langchain.com/")


if __name__ == "__main__":
    main()
