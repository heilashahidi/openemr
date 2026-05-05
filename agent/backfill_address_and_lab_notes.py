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
    """Parse addresses only when city/state/postal are empty (idempotent).

    If the address has already been split into separate columns we leave it
    alone — re-parsing the trimmed `street` would clobber the other columns.
    """
    print("=== Fix addresses ===")
    out = run_sql(
        "SELECT pid, street, city, state, postal_code FROM patient_data WHERE pid IN (10,11,12,13);"
    )
    for line in out.strip().split("\n")[1:]:
        cells = line.split("\t")
        pid = cells[0]
        blob = cells[1] if len(cells) > 1 else ""
        city = cells[2] if len(cells) > 2 else ""
        if city.strip():
            print(f"  pid={pid}: already split, skipping")
            continue
        street, city, state, postal = parse_address(blob)
        run_sql(
            f"UPDATE patient_data SET street='{escape_sql(street)}', city='{escape_sql(city)}', "
            f"state='{escape_sql(state)}', postal_code='{escape_sql(postal)}' WHERE pid={pid};"
        )
        print(f"  pid={pid}: {street} | {city} | {state} | {postal}")


def backfill_lab_metadata():
    print("\n=== Re-extract labs for interpretive comments + specimen info ===")
    for pid, path in LABS:
        print(f"\n  pid={pid} {os.path.basename(path)}")
        result = extract_document(path, "lab_pdf")
        if not result.get("success"):
            print(f"    ❌ Extraction failed: {result.get('error')}")
            continue
        ext = result["extraction"]

        # Specimen → procedure_order
        spec_type = ext.get("specimen_type") or ""
        spec_vol = ext.get("specimen_volume") or ""
        if spec_type or spec_vol:
            run_sql(
                f"UPDATE procedure_order SET specimen_type='{escape_sql(spec_type)}', "
                f"specimen_volume='{escape_sql(spec_vol)}' WHERE patient_id={pid};"
            )
            print(f"    ✅ specimen: {spec_type} / {spec_vol}")

        # Interpretive + specimen notes → procedure_report
        spec_notes = (ext.get("specimen_notes") or "").strip()
        interp = (ext.get("interpretive_comments") or "").strip()
        combined = "\n\n".join(p for p in [
            f"Specimen notes: {spec_notes}" if spec_notes else "",
            interp,
        ] if p)
        if combined:
            run_sql(
                f"UPDATE procedure_report pr "
                f"JOIN procedure_order po ON po.procedure_order_id = pr.procedure_order_id "
                f"SET pr.report_notes = '{escape_sql(combined)}' "
                f"WHERE po.patient_id = {pid};"
            )
            print(f"    ✅ report_notes ({len(combined)} chars)")


if __name__ == "__main__":
    fix_addresses()
    backfill_lab_metadata()
