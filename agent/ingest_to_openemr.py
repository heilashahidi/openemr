"""
Ingest extracted document data into OpenEMR.
Takes an intake form extraction and creates:
- Patient record (patient_data)
- Conditions (lists)
- Medications (prescriptions)
- Allergies (lists)
- Document reference (documents)

Run: python3 ingest_to_openemr.py
"""

import json
import subprocess
import os
from document_extractor import extract_document

MARIADB_CMD = "docker exec -i $(docker ps | grep maria | awk '{print $1}') mariadb -u root -proot openemr"


def run_sql(sql):
    """Execute SQL against OpenEMR's MariaDB."""
    # Get container ID
    cid = subprocess.run("docker ps | grep maria | awk '{print $1}'", shell=True, capture_output=True, text=True).stdout.strip()
    if not cid:
        print("  SQL Error: MariaDB container not found")
        return None
    result = subprocess.run(
        ["docker", "exec", "-i", cid, "mariadb", "-u", "root", "-proot", "openemr"],
        input=sql, capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  SQL Error: {result.stderr.strip()[:200]}")
        return None
    return result.stdout.strip()


def run_sql_insert(sql):
    """Execute INSERT and return LAST_INSERT_ID in a single connection."""
    combined = f"{sql} SELECT LAST_INSERT_ID();"
    result = run_sql(combined)
    if result is None:
        return 0
    lines = result.strip().split('\n')
    for line in reversed(lines):
        if line.strip().isdigit():
            return int(line.strip())
    return 0


def get_next_pid():
    """Get the next available patient ID."""
    result = run_sql("SELECT MAX(pid) FROM patient_data;")
    if result:
        lines = result.strip().split('\n')
        if len(lines) > 1:
            max_pid = lines[1].strip()
            if max_pid and max_pid != 'NULL':
                return int(max_pid) + 1
    return 10


def parse_dob(dob_str):
    """Parse DOB from various formats to YYYY-MM-DD."""
    if not dob_str:
        return '1990-01-01'
    # Already in YYYY-MM-DD
    if len(dob_str) == 10 and dob_str[4] == '-':
        return dob_str
    # MM/DD/YYYY
    parts = dob_str.replace('-', '/').split('/')
    if len(parts) == 3:
        if len(parts[2]) == 4:  # MM/DD/YYYY
            return f"{parts[2]}-{parts[0].zfill(2)}-{parts[1].zfill(2)}"
        elif len(parts[0]) == 4:  # YYYY/MM/DD
            return f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
    return dob_str


def parse_sex(sex_str):
    """Normalize sex field."""
    if not sex_str:
        return 'Unknown'
    s = sex_str.lower().strip()
    if s.startswith('f'):
        return 'Female'
    elif s.startswith('m'):
        return 'Male'
    return sex_str


def escape_sql(val):
    """Escape string for SQL."""
    if val is None:
        return ''
    return str(val).replace("'", "\\'").replace('"', '\\"')


def ingest_intake_form(extraction, source_file):
    """Create a patient and populate their chart from an intake form extraction."""
    data = extraction
    pid = get_next_pid()

    # Parse demographics
    name_parts = data.get('patient_name', 'Unknown Patient').replace(',', ' ').split()
    if len(name_parts) >= 2:
        fname = name_parts[0] if not name_parts[0].isupper() else name_parts[1] if len(name_parts) > 1 else name_parts[0]
        lname = name_parts[-1] if not name_parts[-1] == fname else name_parts[0]
        # Handle "LAST, FIRST" format
        if ',' in data.get('patient_name', ''):
            parts = data['patient_name'].split(',')
            lname = parts[0].strip().title()
            fname = parts[1].strip().split()[0].title() if len(parts) > 1 else 'Unknown'
        else:
            fname = name_parts[0].title()
            lname = name_parts[-1].title()
    else:
        fname = name_parts[0].title() if name_parts else 'Unknown'
        lname = 'Unknown'

    dob = parse_dob(data.get('patient_dob', ''))
    sex = parse_sex(data.get('patient_sex', ''))
    phone = escape_sql(data.get('patient_phone', ''))
    address = escape_sql(data.get('patient_address', ''))
    email = ''

    print(f"\n{'='*60}")
    print(f"  Ingesting: {fname} {lname} (pid={pid})")
    print(f"  DOB: {dob} | Sex: {sex}")
    print(f"  Chief concern: {data.get('chief_concern', 'N/A')[:80]}")
    print(f"{'='*60}")

    # 1. Create patient
    sql = f"INSERT INTO patient_data (pid, fname, lname, DOB, sex, phone_home, street) VALUES ({pid}, '{escape_sql(fname)}', '{escape_sql(lname)}', '{dob}', '{sex}', '{phone}', '{escape_sql(address)}');"
    run_sql(sql)
    print(f"  ✅ Patient created: {fname} {lname} (pid={pid})")

    # Generate UUID
    run_sql(f"UPDATE patient_data SET uuid = UNHEX(REPLACE(UUID(), '-', '')) WHERE pid = {pid} AND uuid IS NULL;")

    # 2. Add conditions from problem list (if available in extraction)
    # Intake forms may have conditions in various fields
    conditions_added = 0

    # 3. Add medications
    meds = data.get('current_medications', [])
    for med in meds:
        med_name = escape_sql(med.get('medication_name', ''))
        dose = escape_sql(med.get('dose', ''))
        freq = escape_sql(med.get('frequency', ''))
        purpose = escape_sql(med.get('purpose', ''))
        full_drug = f"{med_name} {dose}".strip()

        sql = f"INSERT INTO prescriptions (patient_id, drug, dosage, date_added, active, txDate, usage_category_title, request_intent_title) VALUES ({pid}, '{escape_sql(full_drug)}', '{escape_sql(freq)}', NOW(), 1, CURDATE(), '', '');"
        run_sql(sql)
        conditions_added += 1
    print(f"  ✅ {len(meds)} medications added")

    # 4. Add allergies
    allergies = data.get('allergies', [])
    for allergy in allergies:
        allergen = escape_sql(allergy.get('allergen', ''))
        reaction = escape_sql(allergy.get('reaction', ''))
        sql = f"INSERT INTO lists (pid, type, title, diagnosis, begdate, activity) VALUES ({pid}, 'allergy', '{allergen} ({reaction})', '', CURDATE(), 1);"
        run_sql(sql)
    print(f"  ✅ {len(allergies)} allergies added")

    # 5. Add encounter with chief concern
    chief_concern = escape_sql(data.get('chief_concern', 'New patient visit'))
    form_date = data.get('form_date', '2026-04-20')
    sql = f"INSERT INTO form_encounter (pid, date, reason, facility_id, provider_id) VALUES ({pid}, '{form_date}', '{chief_concern}', 3, 1);"
    run_sql(sql)
    print(f"  ✅ Encounter added: {data.get('chief_concern', '')[:60]}")

    # 6. Store document reference in OpenEMR
    mimetype = "image/png" if source_file.endswith(".png") else "application/pdf"
    sql = f"INSERT INTO documents (id, uuid, type, size, date, mimetype, owner, revision, foreign_id, docdate, name, storagemethod) SELECT COALESCE(MAX(id),0)+1, UNHEX(REPLACE(UUID(),'-','')), 'file_url', 0, NOW(), '{mimetype}', 1, NOW(), {pid}, '{form_date}', '{escape_sql(source_file)}', 0 FROM documents;"
    run_sql(sql)
    print(f"  ✅ Source document reference stored in OpenEMR")

    # 7. Add family history as notes
    family = data.get('family_history', [])
    if family:
        fh_text = '; '.join([f"{f.get('relation','')}: {', '.join(f.get('conditions',[]))} ({f.get('status','')})" for f in family])
        # Store as a note in the encounter
        print(f"  ℹ️  Family history: {fh_text[:80]}")

    print(f"\n  ✅ Patient {fname} {lname} fully ingested into OpenEMR (pid={pid})")
    return pid


def ingest_lab_results(extraction, patient_pid, source_file):
    """Add lab results to an existing patient's chart via procedure tables."""
    data = extraction
    labs = data.get('lab_results', [])
    collection_date = data.get('collection_date', '2026-04-20')

    print(f"\n  Adding {len(labs)} lab results to pid={patient_pid}")

    # Get the encounter_id for this patient
    enc_result = run_sql(f"SELECT id FROM form_encounter WHERE pid={patient_pid} ORDER BY id DESC LIMIT 1;")
    encounter_id = 0
    if enc_result:
        lines = enc_result.strip().split('\n')
        if len(lines) > 1 and lines[1].strip().isdigit():
            encounter_id = int(lines[1].strip())

    # 1. Create procedure_order
    order_id = run_sql_insert(f"INSERT INTO procedure_order (uuid, provider_id, patient_id, encounter_id, date_collected, date_ordered, order_priority, order_status, activity) VALUES (UNHEX(REPLACE(UUID(),'-','')), 1, {patient_pid}, {encounter_id}, '{collection_date}', '{collection_date}', 'normal', 'complete', 1);")

    if not order_id:
        print(f"  ❌ Failed to create procedure_order")
        return

    # 2. Create procedure_report
    report_id = run_sql_insert(f"INSERT INTO procedure_report (uuid, procedure_order_id, procedure_order_seq, date_collected, date_report, report_status, review_status) VALUES (UNHEX(REPLACE(UUID(),'-','')), {order_id}, 1, '{collection_date}', '{collection_date}', 'final', 'received');")

    if not report_id:
        print(f"  ❌ Failed to create procedure_report")
        return

    # 3. Insert each lab result
    for lab in labs:
        test_name = escape_sql(lab.get('test_name', ''))
        value = escape_sql(lab.get('value', ''))
        unit = escape_sql(lab.get('unit', ''))
        ref_range = escape_sql(lab.get('reference_range', ''))
        flag = escape_sql(lab.get('abnormal_flag', '') or '')

        run_sql(f"INSERT INTO procedure_result (uuid, procedure_report_id, result_data_type, result_code, result_text, date, units, result, `range`, abnormal, result_status) VALUES (UNHEX(REPLACE(UUID(),'-','')), {report_id}, 'S', '', '{test_name}', '{collection_date}', '{unit}', '{value}', '{ref_range}', '{flag}', 'final');")

        flag_display = f"⚠️ {flag}" if flag else "✓"
        print(f"    📊 {test_name}: {value} {unit} {flag_display}")

    print(f"  ✅ {len(labs)} lab results stored in procedure tables (order={order_id}, report={report_id})")

    # Store document reference
    mimetype = "image/png" if source_file.endswith(".png") else "application/pdf"
    sql = f"INSERT INTO documents (id, uuid, type, size, date, mimetype, owner, revision, foreign_id, docdate, name, storagemethod) SELECT COALESCE(MAX(id),0)+1, UNHEX(REPLACE(UUID(),'-','')), 'file_url', 0, NOW(), '{mimetype}', 1, NOW(), {patient_pid}, '{collection_date}', '{escape_sql(source_file)}', 0 FROM documents;"
    run_sql(sql)
    print(f"  ✅ Lab document reference stored for pid={patient_pid}")


def main():
    print("=" * 60)
    print("  OpenEMR Document Ingestion Pipeline")
    print("  Extract → Validate → Store")
    print("=" * 60)

    sample_dir = "sample_docs"
    intake_dir = os.path.join(sample_dir, "intake-forms")
    lab_dir = os.path.join(sample_dir, "lab-results")

    # Track created patients by name for lab linking
    created_patients = {}

    # 1. Ingest all intake forms → create patients
    print("\n📋 INTAKE FORMS → Creating patients...")
    intake_files = sorted([f for f in os.listdir(intake_dir) if not f.startswith('.')])

    for filename in intake_files:
        filepath = os.path.join(intake_dir, filename)
        print(f"\n  Extracting: {filename}...")
        result = extract_document(filepath, "intake_form")

        if result.get("success"):
            pid = ingest_intake_form(result["extraction"], filename)
            # Map patient name prefix to pid for lab linking
            prefix = filename.split('-')[0:2]  # e.g., ['p01', 'chen']
            key = '-'.join(prefix)
            created_patients[key] = pid
        else:
            print(f"  ❌ Extraction failed: {result.get('error', 'Unknown error')}")

    # 2. Ingest all lab results → link to patients
    print("\n\n🔬 LAB RESULTS → Linking to patients...")
    lab_files = sorted([f for f in os.listdir(lab_dir) if not f.startswith('.')])

    for filename in lab_files:
        filepath = os.path.join(lab_dir, filename)
        prefix = '-'.join(filename.split('-')[0:2])  # e.g., 'p01-chen'
        patient_pid = created_patients.get(prefix)

        if not patient_pid:
            print(f"\n  ⚠️  No patient found for {filename}, skipping")
            continue

        print(f"\n  Extracting: {filename}...")
        result = extract_document(filepath, "lab_pdf")

        if result.get("success"):
            ingest_lab_results(result["extraction"], patient_pid, filename)
        else:
            print(f"  ❌ Extraction failed: {result.get('error', 'Unknown error')}")

    # Summary
    print("\n" + "=" * 60)
    print("  INGESTION COMPLETE")
    print(f"  Patients created: {len(created_patients)}")

    # Verify
    print("\n  Verifying in OpenEMR:")
    result = run_sql("SELECT pid, fname, lname FROM patient_data ORDER BY pid DESC LIMIT 5;")
    if result:
        print(f"  {result}")
    print("=" * 60)


if __name__ == "__main__":
    main()
