"""One-shot: parse addresses on existing patients and re-extract lab interpretive comments.

Run after the schema/script changes that added `parse_address` and
`interpretive_comments`.
"""
import os

# Load .env so the extractor's API key is available.
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    for line in open(env_path):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v.strip().strip('"').strip("'"))

from document_extractor import extract_document
from ingest_to_openemr import parse_address, run_sql, escape_sql

LABS = [
    (10, "sample_docs/lab-results/p01-chen-lipid-panel.pdf"),
    (11, "sample_docs/lab-results/p02-whitaker-cbc.pdf"),
    (12, "sample_docs/lab-results/p03-reyes-hba1c.png"),
    (13, "sample_docs/lab-results/p04-kowalski-cmp.pdf"),
]


def fix_addresses():
    print("=== Fix addresses ===")
    out = run_sql("SELECT pid, street FROM patient_data WHERE pid IN (10,11,12,13);")
    for line in out.strip().split("\n")[1:]:
        pid, blob = line.split("\t", 1)
        street, city, state, postal = parse_address(blob)
        run_sql(
            f"UPDATE patient_data SET street='{escape_sql(street)}', city='{escape_sql(city)}', "
            f"state='{escape_sql(state)}', postal_code='{escape_sql(postal)}' WHERE pid={pid};"
        )
        print(f"  pid={pid}: {street} | {city} | {state} | {postal}")


def backfill_interpretive_comments():
    print("\n=== Re-extract labs for interpretive comments ===")
    for pid, path in LABS:
        print(f"\n  pid={pid} {os.path.basename(path)}")
        result = extract_document(path, "lab_pdf")
        if not result.get("success"):
            print(f"    ❌ Extraction failed: {result.get('error')}")
            continue
        comments = result["extraction"].get("interpretive_comments")
        if not comments:
            print("    (no interpretive comments in source)")
            continue

        # Update the procedure_report for this patient's most recent order
        run_sql(
            f"UPDATE procedure_report pr "
            f"JOIN procedure_order po ON po.procedure_order_id = pr.procedure_order_id "
            f"SET pr.report_notes = '{escape_sql(comments)}' "
            f"WHERE po.patient_id = {pid};"
        )
        print(f"    ✅ saved ({len(comments)} chars): {comments[:90]}...")


if __name__ == "__main__":
    fix_addresses()
    backfill_interpretive_comments()
