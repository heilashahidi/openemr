"""One-shot: compute bbox_json for derived_fact_citations rows that already exist.

Run after adding the bbox_json column. Idempotent — only updates rows where
bbox_json is currently NULL or empty. PNG sources are skipped (PyMuPDF text
search doesn't apply to images).
"""
import json

from ingest_to_openemr import _compute_bboxes, _document_source_path, run_sql, escape_sql


def main():
    out = run_sql(
        "SELECT id, document_id, quote_or_value FROM derived_fact_citations "
        "WHERE bbox_json IS NULL OR bbox_json = '';"
    ) or ""
    lines = [l for l in out.strip().split("\n") if l]
    if len(lines) < 2:
        print("Nothing to backfill (no NULL bbox_json rows).")
        return

    n_done = 0
    n_skip = 0
    by_status = {"matched": 0, "no_quote": 0, "image": 0, "no_match": 0}

    for line in lines[1:]:
        cells = line.split("\t")
        if len(cells) < 3:
            continue
        cid = cells[0]
        doc_id = cells[1]
        quote = "\t".join(cells[2:])  # quote could itself contain tabs

        if not quote.strip():
            by_status["no_quote"] += 1
            n_skip += 1
            continue

        path = _document_source_path(int(doc_id))
        if not path:
            n_skip += 1
            continue
        if not path.lower().endswith(".pdf"):
            by_status["image"] += 1
            n_skip += 1
            continue

        bboxes = _compute_bboxes(path, quote)
        if not bboxes:
            by_status["no_match"] += 1
            run_sql(
                f"UPDATE derived_fact_citations SET bbox_json='[]' WHERE id={cid};"
            )
            continue

        bbox_json = escape_sql(json.dumps(bboxes))
        run_sql(
            f"UPDATE derived_fact_citations SET bbox_json='{bbox_json}' WHERE id={cid};"
        )
        by_status["matched"] += 1
        n_done += 1

    print(f"  matched : {by_status['matched']:3d}  (rows updated with bbox)")
    print(f"  no_match: {by_status['no_match']:3d}  (PDF searched, quote not found — set to '[]')")
    print(f"  image   : {by_status['image']:3d}  (PNG source — skipped)")
    print(f"  no_quote: {by_status['no_quote']:3d}  (empty quote_or_value)")
    print(f"\n  total updated with non-empty bbox: {n_done}")
    print(f"  total skipped: {n_skip}")


if __name__ == "__main__":
    main()
