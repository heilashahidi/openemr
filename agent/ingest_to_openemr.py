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

import hashlib
import json
import re
import subprocess
import os
import uuid as uuidlib
from document_extractor import extract_document

MARIADB_CMD = "docker exec -i $(docker ps | grep maria | awk '{print $1}') mariadb -u root -proot openemr"
OEMR_DOC_REPO = "/var/www/localhost/htdocs/openemr/sites/default/documents"


def find_openemr_container():
    """Container ID for the OpenEMR webserver (image openemr/openemr)."""
    out = subprocess.run(
        "docker ps --format '{{.ID}} {{.Image}}' | grep openemr/openemr",
        shell=True, capture_output=True, text=True,
    ).stdout.strip()
    return out.split()[0] if out else None


def find_existing_document(filename):
    """Return (doc_id, foreign_id_pid) if a document with this name already exists, else None.

    Used as the idempotency key — a sample file uniquely identifies a patient
    (intake) or a lab batch.
    """
    safe = escape_sql(filename)
    result = run_sql(f"SELECT id, foreign_id FROM documents WHERE name='{safe}' AND deleted=0 LIMIT 1;")
    if not result:
        return None
    lines = result.strip().split('\n')
    if len(lines) < 2:
        return None
    parts = lines[1].split('\t')
    if len(parts) < 2 or not parts[0].strip().isdigit():
        return None
    return int(parts[0]), int(parts[1])


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


def parse_address(addr_str):
    """Split an address blob into (street, city, state, postal_code).

    Expected pattern:
        "<street>, [<unit>,] <city>, <STATE> <ZIP>"
    Returns the full input as `street` if parsing fails.
    """
    if not addr_str:
        return ("", "", "", "")
    parts = [p.strip() for p in addr_str.split(",") if p.strip()]
    if len(parts) < 3:
        return (addr_str, "", "", "")
    state_zip = parts[-1].split()
    if len(state_zip) >= 2 and len(state_zip[0]) == 2:
        state = state_zip[0]
        postal = " ".join(state_zip[1:])
        city = parts[-2]
        street = ", ".join(parts[:-2])
        return (street, city, state, postal)
    return (addr_str, "", "", "")


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


RELATION_TO_COLUMN = {
    'mother': 'history_mother',
    'mom': 'history_mother',
    'father': 'history_father',
    'dad': 'history_father',
    'sister': 'history_siblings',
    'brother': 'history_siblings',
    'sibling': 'history_siblings',
    'siblings': 'history_siblings',
    'son': 'history_offspring',
    'daughter': 'history_offspring',
    'child': 'history_offspring',
    'children': 'history_offspring',
    'offspring': 'history_offspring',
    'spouse': 'history_spouse',
    'husband': 'history_spouse',
    'wife': 'history_spouse',
    'partner': 'history_spouse',
}


def populate_family_history(pid, family_history):
    """Map extracted family_history entries to OpenEMR's history_data columns.

    OpenEMR stores family history per-relation in `history_data` as free text
    (history_mother, history_father, history_siblings, history_offspring,
    history_spouse). Anything that doesn't map to one of these (grandparent,
    aunt, uncle, etc.) is appended to `additional_history`.
    """
    if not family_history:
        return

    fields = {}  # column → list[str]
    extras = []
    for entry in family_history:
        relation_raw = (entry.get('relation') or '').strip().lower()
        conditions = entry.get('conditions') or []
        status = (entry.get('status') or '').strip()

        text = ', '.join(conditions) if conditions else '(no conditions reported)'
        if status:
            text = f"{text} ({status})"

        col = RELATION_TO_COLUMN.get(relation_raw)
        if col:
            fields.setdefault(col, []).append(text)
        else:
            extras.append(f"{entry.get('relation','Relative')}: {text}")

    if extras:
        fields.setdefault('additional_history', []).append('; '.join(extras))

    # Upsert: history_data has at most one row per pid (no UNIQUE constraint
    # in older schemas, but the UI updates a single row).
    existing = run_sql(f"SELECT id FROM history_data WHERE pid={pid} LIMIT 1;")
    has_row = existing and len(existing.strip().split('\n')) > 1

    set_clauses = ", ".join(
        f"{col}='{escape_sql(' / '.join(values))}'"
        for col, values in fields.items()
    )
    if has_row:
        run_sql(f"UPDATE history_data SET {set_clauses} WHERE pid={pid};")
    else:
        cols = ", ".join(fields.keys())
        vals = ", ".join(f"'{escape_sql(' / '.join(v))}'" for v in fields.values())
        run_sql(f"INSERT INTO history_data (pid, uuid, date, {cols}) VALUES ({pid}, UNHEX(REPLACE(UUID(),'-','')), NOW(), {vals});")
    print(f"  ✅ Family history populated ({len(family_history)} entries → {len(fields)} columns)")


def populate_emergency_contact(pid, ec_text):
    """Parse 'Name (Relationship) - Phone' and write to patient_data.

    OpenEMR has phone_contact + contact_relationship; no dedicated name field,
    so the name is folded into contact_relationship.
    """
    if not ec_text:
        return
    # Pull out a phone number
    phone_match = re.search(r'\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{4}', ec_text)
    phone = phone_match.group(0) if phone_match else ''
    # Strip phone from text to get name + relationship part
    name_rel = re.sub(r'\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{4}', '', ec_text).strip(' -—')
    run_sql(
        f"UPDATE patient_data SET phone_contact='{escape_sql(phone)}', "
        f"contact_relationship='{escape_sql(name_rel)}' WHERE pid={pid};"
    )
    print(f"  ✅ Emergency contact: {name_rel} / {phone}")


def populate_insurance(pid, ins_text):
    """Insert a single primary insurance_data row from the free-text extraction.

    Pattern handled: '<Provider/Plan> - Member ID: <policy>' (case-insensitive
    label). Falls back to dumping the whole string into `provider` if we can't
    isolate a policy number.
    """
    if not ins_text:
        return
    # Skip values that look like MRNs masquerading as insurance — the LLM
    # sometimes grabs them from forms that have no real insurance section.
    if re.match(r'^\s*MRN[\s\-:]', ins_text, re.IGNORECASE):
        print(f"  ⏭️  Insurance skipped (looks like MRN): {ins_text}")
        return

    provider, policy = ins_text, ''
    m = re.search(r'(?:member\s*id|policy\s*(?:number|#)?|id\s*#?)\s*:?\s*([\w\-]+)', ins_text, re.IGNORECASE)
    if m:
        policy = m.group(1)
        provider = ins_text[:m.start()].strip(' -—:,')
    run_sql(
        f"DELETE FROM insurance_data WHERE pid={pid} AND type='primary';"
    )
    run_sql(
        f"INSERT INTO insurance_data (pid, type, provider, policy_number, date) "
        f"VALUES ({pid}, 'primary', '{escape_sql(provider)}', '{escape_sql(policy)}', CURDATE());"
    )
    print(f"  ✅ Insurance: {provider} / policy={policy}")


def populate_problem_list(pid, conditions, form_date):
    """Insert each condition as a lists row (type='medical_problem')."""
    if not conditions:
        return
    for cond in conditions:
        cond = str(cond).strip()
        if not cond:
            continue
        # Skip if already present (avoid duplicates on re-runs)
        existing = run_sql(
            f"SELECT id FROM lists WHERE pid={pid} AND type='medical_problem' AND title='{escape_sql(cond)}' LIMIT 1;"
        )
        if existing and len(existing.strip().split('\n')) > 1:
            continue
        run_sql(
            f"INSERT INTO lists (pid, type, title, begdate, activity) "
            f"VALUES ({pid}, 'medical_problem', '{escape_sql(cond)}', '{form_date}', 1);"
        )
    print(f"  ✅ Past medical history: {len(conditions)} entries")


def populate_surgical_history(pid, surgeries, form_date):
    """Insert each surgery as a lists row (type='surgery')."""
    if not surgeries:
        return
    for surg in surgeries:
        surg = str(surg).strip()
        if not surg:
            continue
        existing = run_sql(
            f"SELECT id FROM lists WHERE pid={pid} AND type='surgery' AND title='{escape_sql(surg)}' LIMIT 1;"
        )
        if existing and len(existing.strip().split('\n')) > 1:
            continue
        run_sql(
            f"INSERT INTO lists (pid, type, title, begdate, activity) "
            f"VALUES ({pid}, 'surgery', '{escape_sql(surg)}', '{form_date}', 1);"
        )
    print(f"  ✅ Surgical history: {len(surgeries)} entries")


def populate_treating_physicians(pid, physicians_text):
    """Save treating physicians free-text into patient_data.care_team_provider."""
    if not physicians_text:
        return
    run_sql(
        f"UPDATE patient_data SET care_team_provider='{escape_sql(physicians_text)}' WHERE pid={pid};"
    )
    print(f"  ✅ Treating physicians: {physicians_text[:80]}")


def populate_social_history(pid, social_history_text):
    """Save the extracted social history blob into history_data.

    The intake extraction returns social_history as free text. We also try to
    pull out the most common structured columns (tobacco, alcohol, exercise)
    via simple keyword scan; everything else lands in additional_history so it
    is visible in the History panel.
    """
    if not social_history_text:
        return

    blob = social_history_text.strip()
    fields = {'additional_history': blob}

    # Best-effort structured extraction for the columns OpenEMR renders in the
    # Social History panel. Each line/segment that mentions a known topic
    # populates the matching column.
    # Segment on commas, semicolons, and newlines so each topic-tagged phrase
    # ("Tobacco: Never", "Alcohol: 2 drinks/week") becomes its own segment.
    segments = [s.strip() for s in re.split(r'[;,\n]', blob) if s.strip()]
    for seg in segments:
        low = seg.lower()
        if any(k in low for k in ('tobacco', 'smok', 'cigar', 'vape', 'nicotine')):
            fields.setdefault('tobacco', seg)
        elif any(k in low for k in ('alcohol', 'drink', 'beer', 'wine', 'liquor')):
            fields.setdefault('alcohol', seg)
        elif any(k in low for k in ('exercise', 'walk', 'gym', 'jog', 'run ', 'physical activity', 'sedentary', 'active')):
            fields.setdefault('exercise_patterns', seg)
        elif any(k in low for k in ('drug', 'marijuana', 'cocaine', 'recreational')):
            fields.setdefault('recreational_drugs', seg)
        elif any(k in low for k in ('coffee', 'caffeine', 'espresso')):
            fields.setdefault('coffee', seg)
        elif any(k in low for k in ('sleep', 'insomnia')):
            fields.setdefault('sleep_patterns', seg)

    existing = run_sql(f"SELECT id FROM history_data WHERE pid={pid} LIMIT 1;")
    has_row = existing and len(existing.strip().split('\n')) > 1
    set_clauses = ", ".join(f"{c}='{escape_sql(v)}'" for c, v in fields.items())
    if has_row:
        run_sql(f"UPDATE history_data SET {set_clauses} WHERE pid={pid};")
    else:
        cols = ", ".join(fields.keys())
        vals = ", ".join(f"'{escape_sql(v)}'" for v in fields.values())
        run_sql(f"INSERT INTO history_data (pid, uuid, date, {cols}) VALUES ({pid}, UNHEX(REPLACE(UUID(),'-','')), NOW(), {vals});")
    print(f"  ✅ Social history populated ({len(fields)-1} structured fields + additional_history)")


def next_encounter_number():
    """Get next global encounter number (form_encounter.encounter)."""
    result = run_sql("SELECT COALESCE(MAX(encounter), 0)+1 FROM form_encounter;")
    if result:
        lines = result.strip().split('\n')
        if len(lines) > 1 and lines[1].strip().isdigit():
            return int(lines[1].strip())
    return 1


def store_document(pid, source_path, doc_date, category_id):
    """Copy a file into OpenEMR's document storage and register it in the DB.

    Storage convention (see library/classes/Document.class.php):
      <repo>/<pid>/<uuid>   with path_depth=1, url="file://<abs path>".

    drive_encryption is globally on in this dev install, so we set the
    per-document `encrypted` flag to 0 — the file is stored as-is and OpenEMR
    skips the decrypt step on read.
    """
    filename = os.path.basename(source_path)
    mimetype = "image/png" if filename.endswith(".png") else "application/pdf"

    oemr_cid = find_openemr_container()
    if not oemr_cid:
        print("  ⚠️  OpenEMR container not found; storing DB row only")
        oemr_cid = None

    file_uuid = str(uuidlib.uuid4())
    dst_dir = f"{OEMR_DOC_REPO}/{pid}"
    dst_path = f"{dst_dir}/{file_uuid}"
    url = f"file://{dst_path}"

    size = 0
    sha1 = ""
    if oemr_cid and os.path.exists(source_path):
        with open(source_path, "rb") as fh:
            data = fh.read()
        size = len(data)
        sha1 = hashlib.sha1(data).hexdigest()
        subprocess.run(["docker", "exec", oemr_cid, "mkdir", "-p", dst_dir], check=True)
        subprocess.run(["docker", "cp", source_path, f"{oemr_cid}:{dst_path}"], check=True)
        subprocess.run(["docker", "exec", oemr_cid, "chown", "-R", "apache:apache", dst_dir], check=True)
        subprocess.run(["docker", "exec", oemr_cid, "chmod", "0700", dst_dir], check=True)
        subprocess.run(["docker", "exec", oemr_cid, "chmod", "0600", dst_path], check=True)

    doc_id = run_sql_insert(
        f"INSERT INTO documents (uuid, type, size, date, url, mimetype, owner, revision, foreign_id, docdate, name, storagemethod, path_depth, drive_uuid, encrypted, hash) "
        f"VALUES (UNHEX(REPLACE(UUID(),'-','')), 'file_url', {size}, NOW(), '{escape_sql(url)}', '{mimetype}', 1, NOW(), {pid}, '{doc_date}', '{escape_sql(filename)}', 0, 1, "
        f"UNHEX(REPLACE('{file_uuid}','-','')), 0, '{sha1}');"
    )
    if doc_id:
        run_sql(f"INSERT INTO categories_to_documents (category_id, document_id) VALUES ({category_id}, {doc_id});")
    return doc_id


def ingest_intake_form(extraction, source_path):
    """Create a patient and populate their chart from an intake form extraction."""
    source_file = os.path.basename(source_path)

    existing = find_existing_document(source_file)
    if existing:
        existing_pid = existing[1]
        print(f"  ⏭️  Skipping {source_file}: already ingested for pid={existing_pid}")
        return existing_pid

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
    street, city, state, postal = parse_address(data.get('patient_address', ''))
    email = ''

    print(f"\n{'='*60}")
    print(f"  Ingesting: {fname} {lname} (pid={pid})")
    print(f"  DOB: {dob} | Sex: {sex}")
    print(f"  Chief concern: {data.get('chief_concern', 'N/A')[:80]}")
    print(f"{'='*60}")

    # 1. Create patient
    sql = (
        f"INSERT INTO patient_data (pid, fname, lname, DOB, sex, phone_home, street, city, state, postal_code) "
        f"VALUES ({pid}, '{escape_sql(fname)}', '{escape_sql(lname)}', '{dob}', '{sex}', '{phone}', "
        f"'{escape_sql(street)}', '{escape_sql(city)}', '{escape_sql(state)}', '{escape_sql(postal)}');"
    )
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
    encounter_num = next_encounter_number()
    fe_id = run_sql_insert(
        f"INSERT INTO form_encounter (pid, encounter, date, reason, facility_id, provider_id) "
        f"VALUES ({pid}, {encounter_num}, '{form_date}', '{chief_concern}', 3, 1);"
    )
    # Register the encounter in the forms table so it appears in the chart's
    # encounter list (the UI joins forms → form_encounter via form_id).
    run_sql(
        f"INSERT INTO forms (date, encounter, form_name, form_id, pid, formdir, provider_id, deleted) "
        f"VALUES ('{form_date}', {encounter_num}, 'New Patient Encounter', {fe_id}, {pid}, 'newpatient', 1, 0);"
    )
    print(f"  ✅ Encounter #{encounter_num} added: {data.get('chief_concern', '')[:60]}")

    # 6. Store document reference in OpenEMR (Patient Information category)
    store_document(pid, source_path, form_date, category_id=4)
    print(f"  ✅ Source document reference stored in OpenEMR")

    # 7. Family + social history → history_data
    populate_family_history(pid, data.get('family_history', []))
    populate_social_history(pid, data.get('social_history'))

    # 8. Past medical + surgical history → lists
    populate_problem_list(pid, data.get('past_medical_history', []), form_date)
    populate_surgical_history(pid, data.get('surgical_history', []), form_date)

    # 9. Emergency contact, insurance, treating physicians → patient_data / insurance_data
    populate_emergency_contact(pid, data.get('emergency_contact'))
    populate_insurance(pid, data.get('insurance'))
    populate_treating_physicians(pid, data.get('treating_physicians'))

    print(f"\n  ✅ Patient {fname} {lname} fully ingested into OpenEMR (pid={pid})")
    return pid


def ingest_lab_results(extraction, patient_pid, source_path):
    """Add lab results to an existing patient's chart via procedure tables."""
    source_file = os.path.basename(source_path)

    if find_existing_document(source_file):
        print(f"  ⏭️  Skipping {source_file}: lab already ingested for pid={patient_pid}")
        return

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
    interp = escape_sql(data.get('interpretive_comments') or '')
    report_id = run_sql_insert(
        f"INSERT INTO procedure_report (uuid, procedure_order_id, procedure_order_seq, date_collected, date_report, report_status, review_status, report_notes) "
        f"VALUES (UNHEX(REPLACE(UUID(),'-','')), {order_id}, 1, '{collection_date}', '{collection_date}', 'final', 'received', '{interp}');"
    )

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

    # Store document reference (Lab Report category)
    store_document(patient_pid, source_path, collection_date, category_id=2)
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
        prefix = '-'.join(filename.split('-')[0:2])  # e.g., 'p01-chen'

        existing = find_existing_document(filename)
        if existing:
            print(f"\n  ⏭️  Skipping {filename}: already ingested for pid={existing[1]}")
            created_patients[prefix] = existing[1]
            continue

        print(f"\n  Extracting: {filename}...")
        result = extract_document(filepath, "intake_form")

        if result.get("success"):
            pid = ingest_intake_form(result["extraction"], filepath)
            created_patients[prefix] = pid
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

        if find_existing_document(filename):
            print(f"\n  ⏭️  Skipping {filename}: lab already ingested for pid={patient_pid}")
            continue

        print(f"\n  Extracting: {filename}...")
        result = extract_document(filepath, "lab_pdf")

        if result.get("success"):
            ingest_lab_results(result["extraction"], patient_pid, filepath)
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
