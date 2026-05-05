"""One-shot: re-extract intake forms for pids 10-13 and populate history_data.

The original ingestion only printed family_history; this fills it in so the
chart's Family History panel renders correctly.
"""
import os

# Load .env so ANTHROPIC_API_KEY is set before importing the extractor.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        for line in open(env_path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v.strip().strip('"').strip("'"))

from document_extractor import extract_document
from ingest_to_openemr import (
    populate_family_history, populate_social_history,
    populate_emergency_contact, populate_insurance,
    populate_problem_list, populate_surgical_history,
    populate_treating_physicians,
)

INTAKES = [
    (10, "sample_docs/intake-forms/p01-chen-intake-typed.pdf"),
    (11, "sample_docs/intake-forms/p02-whitaker-intake.pdf"),
    (12, "sample_docs/intake-forms/p03-reyes-intake.png"),
    (13, "sample_docs/intake-forms/p04-kowalski-intake.png"),
]


def main():
    for pid, path in INTAKES:
        print(f"\n--- pid={pid} {os.path.basename(path)} ---")
        result = extract_document(path, "intake_form")
        if not result.get("success"):
            print(f"  ❌ Extraction failed: {result.get('error')}")
            continue
        family = result["extraction"].get("family_history") or []
        print(f"  Extracted {len(family)} family_history entries")
        for f in family:
            print(f"    - {f.get('relation')}: {f.get('conditions')} ({f.get('status')})")
        populate_family_history(pid, family)

        ext = result["extraction"]
        if ext.get("social_history"):
            populate_social_history(pid, ext["social_history"])
        populate_emergency_contact(pid, ext.get("emergency_contact"))
        populate_insurance(pid, ext.get("insurance"))
        populate_treating_physicians(pid, ext.get("treating_physicians"))

        form_date = ext.get("form_date") or "2026-04-20"
        populate_problem_list(pid, ext.get("past_medical_history") or [], form_date)
        populate_surgical_history(pid, ext.get("surgical_history") or [], form_date)


if __name__ == "__main__":
    main()
