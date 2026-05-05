"""One-shot: link every already-ingested derived fact for pids 10-13 back to
its source document.

For each patient we know the two source docs (intake PDF/PNG and lab PDF/PNG).
We attach a citation row pointing at the appropriate source for every existing
derived fact: prescriptions, allergies (lists), problem list (lists),
surgeries (lists), family/social history (history_data), insurance, encounter
chief concern, lab order/report/results.

This populates `derived_fact_citations` retroactively without re-ingesting.
"""
from ingest_to_openemr import add_citation, run_sql

PATIENTS = [10, 11, 12, 13]


def doc_ids_for(pid):
    """Return (intake_doc_id, lab_doc_id) for a patient."""
    out = run_sql(
        f"SELECT id, name FROM documents WHERE foreign_id={pid} AND deleted=0 ORDER BY id;"
    )
    intake_id, lab_id = None, None
    for line in out.strip().split("\n")[1:]:
        cells = line.split("\t")
        if len(cells) < 2:
            continue
        did = int(cells[0])
        name = cells[1]
        if "intake" in name.lower():
            intake_id = did
        else:
            lab_id = did
    return intake_id, lab_id


def existing_citations_target_set():
    """Set of (target_table, target_id) already cited — keep idempotent."""
    out = run_sql("SELECT target_table, target_id FROM derived_fact_citations;")
    s = set()
    for line in out.strip().split("\n")[1:]:
        cells = line.split("\t")
        if len(cells) >= 2:
            s.add((cells[0], int(cells[1])))
    return s


def cite_table_rows(query, target_table, document_id, field, already):
    out = run_sql(query)
    rows = out.strip().split("\n")[1:]
    n = 0
    for line in rows:
        cells = line.split("\t")
        if not cells or not cells[0].isdigit():
            continue
        target_id = int(cells[0])
        if (target_table, target_id) in already:
            continue
        quote = cells[1] if len(cells) > 1 else ""
        add_citation(target_table, target_id, document_id,
                     citation={'field_or_chunk_id': field, 'quote_or_value': quote})
        already.add((target_table, target_id))
        n += 1
    return n


def main():
    already = existing_citations_target_set()
    print(f"Existing citations: {len(already)} target rows already cited\n")

    for pid in PATIENTS:
        intake_id, lab_id = doc_ids_for(pid)
        print(f"--- pid={pid}  intake_doc={intake_id}  lab_doc={lab_id} ---")
        if not intake_id or not lab_id:
            print("  (missing one of the documents, skipping)")
            continue

        # Intake-derived facts
        n = cite_table_rows(
            f"SELECT id, CONCAT(drug,' ',dosage) FROM prescriptions WHERE patient_id={pid};",
            'prescriptions', intake_id, 'current_medications', already)
        print(f"  prescriptions: {n}")

        n = cite_table_rows(
            f"SELECT id, title FROM lists WHERE pid={pid} AND type='allergy' AND activity=1;",
            'lists', intake_id, 'allergies', already)
        print(f"  allergies: {n}")

        n = cite_table_rows(
            f"SELECT id, title FROM lists WHERE pid={pid} AND type='medical_problem' AND activity=1;",
            'lists', intake_id, 'past_medical_history', already)
        print(f"  problems: {n}")

        n = cite_table_rows(
            f"SELECT id, title FROM lists WHERE pid={pid} AND type='surgery' AND activity=1;",
            'lists', intake_id, 'surgical_history', already)
        print(f"  surgeries: {n}")

        n = cite_table_rows(
            f"SELECT id, COALESCE(history_father,'') FROM history_data WHERE pid={pid};",
            'history_data', intake_id, 'family_and_social_history', already)
        print(f"  history_data: {n}")

        n = cite_table_rows(
            f"SELECT id, provider FROM insurance_data WHERE pid={pid};",
            'insurance_data', intake_id, 'insurance', already)
        print(f"  insurance: {n}")

        n = cite_table_rows(
            f"SELECT id, LEFT(reason,200) FROM form_encounter WHERE pid={pid};",
            'form_encounter', intake_id, 'chief_concern', already)
        print(f"  encounter: {n}")

        # patient_data — emergency contact + treating physicians both live on
        # the patient row; one citation row suffices to point at the source.
        if ('patient_data', pid) not in already:
            add_citation('patient_data', pid, intake_id,
                         citation={'field_or_chunk_id': 'emergency_contact_and_care_team',
                                   'quote_or_value': '(see source intake form)'})
            already.add(('patient_data', pid))
            print(f"  patient_data: 1")

        # Lab-derived facts
        n = cite_table_rows(
            f"SELECT po.procedure_order_id, CONCAT(po.specimen_type,' / ',po.specimen_volume) "
            f"FROM procedure_order po WHERE po.patient_id={pid};",
            'procedure_order', lab_id, 'specimen', already)
        print(f"  procedure_order: {n}")

        n = cite_table_rows(
            f"SELECT pr.procedure_report_id, LEFT(pr.report_notes,200) FROM procedure_report pr "
            f"JOIN procedure_order po ON po.procedure_order_id=pr.procedure_order_id "
            f"WHERE po.patient_id={pid};",
            'procedure_report', lab_id, 'interpretive_comments', already)
        print(f"  procedure_report: {n}")

        n = cite_table_rows(
            f"SELECT pres.procedure_result_id, CONCAT(pres.result_text,'=',pres.result,' ',pres.units) "
            f"FROM procedure_result pres "
            f"JOIN procedure_report rep ON rep.procedure_report_id=pres.procedure_report_id "
            f"JOIN procedure_order po ON po.procedure_order_id=rep.procedure_order_id "
            f"WHERE po.patient_id={pid};",
            'procedure_result', lab_id, 'lab_results', already)
        print(f"  procedure_result: {n}")
        print()


if __name__ == "__main__":
    main()
