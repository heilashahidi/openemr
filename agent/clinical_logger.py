"""Structured per-encounter logger with PHI redaction.

Every call to clinical_graph.run() emits one JSONL record to
agent/logs/encounters-YYYY-MM-DD.jsonl with the fields required by the
W2 spec:
  - tool_sequence
  - latency_per_step_ms
  - tokens_used
  - cost_estimate_usd
  - retrieval_hits
  - extraction_confidence
  - eval_outcome (if running under the eval suite)

Before write, every string value is run through `redact_phi()` so raw
patient names, DOBs, MRNs, phone numbers, ZIPs, and SSNs cannot leak.
The eval suite has dedicated cases (no_phi_in_logs bucket) that grep
the produced log files to verify the redactor holds.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

# Logs directory. We try to create it next to this module, but in CI the
# previous (Docker-based) seed step can leave the parent owned by root —
# `mkdir` then raises PermissionError on import. Fall back to /tmp so the
# whole agent doesn't refuse to import. Local dev keeps the in-tree path.
def _resolve_logs_dir() -> Path:
    primary = Path(__file__).parent / "logs"
    try:
        primary.mkdir(parents=True, exist_ok=True)
        return primary
    except (PermissionError, OSError):
        fallback = Path(os.getenv("OPENEMR_AGENT_LOGS_DIR", "/tmp/openemr-agent-logs"))
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

LOGS_DIR = _resolve_logs_dir()

# Anthropic Claude Sonnet 4.5 pricing (USD per million tokens) — used for the
# per-encounter cost_estimate field. Values current as of W2 build.
PRICE_PER_M_INPUT = 3.00
PRICE_PER_M_OUTPUT = 15.00

# ── PHI patterns ──────────────────────────────────────────────────────────
# Order matters: longer / more-specific patterns first so the generic ones
# don't eat them.

_SSN_RE   = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_PHONE_RE = re.compile(r"\b\(?\d{3}\)?[\s\-.]\s*\d{3}[\s\-.]\d{4}\b")
_MRN_RE   = re.compile(r"\bMRN[\s:#\-]*\d{3,}\b", re.IGNORECASE)
_DOB_RE   = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b")
_ZIP_RE   = re.compile(r"\b\d{5}(?:-\d{4})?\b")

# Names are sourced lazily from `patient_data` so the redactor knows which
# strings to mask. Cached at module level after first DB hit.
_NAME_PATTERN: Optional[re.Pattern] = None
_ADDRESS_PATTERN: Optional[re.Pattern] = None


def _load_phi_lookups() -> None:
    """Populate name + address patterns from the patient_data table.

    Called lazily on first redact_phi() call so module import doesn't
    require a live DB. Failures are silent: if the lookup fails the
    redactor still scrubs phone/DOB/MRN/SSN/ZIP via regex.
    """
    global _NAME_PATTERN, _ADDRESS_PATTERN
    try:
        from ingest_to_openemr import run_sql
        out = run_sql("SELECT fname, lname, street FROM patient_data;") or ""
    except Exception:
        return

    names: set[str] = set()
    streets: set[str] = set()
    for line in out.strip().split("\n")[1:]:
        cells = line.split("\t")
        if len(cells) < 2:
            continue
        for n in (cells[0], cells[1]):
            n = (n or "").strip()
            if len(n) > 2 and n.lower() not in ("null", "unknown"):
                names.add(n)
        if len(cells) >= 3:
            s = (cells[2] or "").strip()
            if len(s) > 4 and s.lower() not in ("null", ""):
                streets.add(s)

    if names:
        pat = r"\b(?:" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")\b"
        _NAME_PATTERN = re.compile(pat, re.IGNORECASE)
    if streets:
        pat = r"(?:" + "|".join(re.escape(s) for s in sorted(streets, key=len, reverse=True)) + r")"
        _ADDRESS_PATTERN = re.compile(pat, re.IGNORECASE)


def redact_phi(text: Any) -> Any:
    """Scrub PHI from a string. Non-strings pass through unchanged."""
    if not isinstance(text, str) or not text:
        return text
    if _NAME_PATTERN is None and _ADDRESS_PATTERN is None:
        _load_phi_lookups()
    s = text
    if _ADDRESS_PATTERN is not None:
        s = _ADDRESS_PATTERN.sub("[ADDRESS]", s)
    if _NAME_PATTERN is not None:
        s = _NAME_PATTERN.sub("[NAME]", s)
    s = _SSN_RE.sub("[SSN]", s)
    s = _PHONE_RE.sub("[PHONE]", s)
    s = _MRN_RE.sub("[MRN]", s)
    s = _DOB_RE.sub("[DATE]", s)
    s = _ZIP_RE.sub("[ZIP]", s)
    return s


def redact_obj(obj: Any) -> Any:
    """Recursively redact PHI from any nested dict/list/string structure."""
    if isinstance(obj, str):
        return redact_phi(obj)
    if isinstance(obj, dict):
        return {k: redact_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_obj(v) for v in obj]
    return obj


def estimate_cost_usd(tokens: dict | None) -> float:
    """Approximate Claude Sonnet 4.5 dollar cost from token counts."""
    if not tokens:
        return 0.0
    inp = tokens.get("input", 0) or 0
    out = tokens.get("output", 0) or 0
    return round(
        (inp / 1_000_000) * PRICE_PER_M_INPUT
        + (out / 1_000_000) * PRICE_PER_M_OUTPUT,
        6,
    )


def log_encounter(record: dict) -> Path:
    """Append one redacted JSON line to today's log file. Returns the path."""
    redacted = redact_obj(record)
    redacted.setdefault("timestamp", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    log_path = LOGS_DIR / f"encounters-{time.strftime('%Y-%m-%d')}.jsonl"
    with open(log_path, "a") as f:
        f.write(json.dumps(redacted, default=str) + "\n")
    return log_path


def latest_log_path() -> Path:
    """Today's log file path (may not exist yet)."""
    return LOGS_DIR / f"encounters-{time.strftime('%Y-%m-%d')}.jsonl"


def read_log_lines(path: Optional[Path] = None) -> list[dict]:
    """Read the encounter log as a list of parsed records (skip bad lines)."""
    p = path or latest_log_path()
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
