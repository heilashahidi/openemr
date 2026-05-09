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


def _document_source_path(document_id):
    """Look up the host filesystem path of the original sample document.

    The `documents.url` column points at the OpenEMR container's storage
    path (not directly accessible from the host). For bbox computation we
    need the source file on the host — luckily our four sample patients
    came from agent/sample_docs/, and `documents.name` is the filename.
    """
    if not document_id:
        return None
    out = run_sql(f"SELECT name FROM documents WHERE id={document_id} LIMIT 1;")
    if not out:
        return None
    lines = out.strip().split("\n")
    if len(lines) < 2:
        return None
    name = lines[1].strip()
    base = os.path.dirname(__file__)
    subdir = "intake-forms" if "intake" in name.lower() else "lab-results"
    candidate = os.path.join(base, "sample_docs", subdir, name)
    return candidate if os.path.exists(candidate) else None


def _compute_bboxes(pdf_path, quote, max_pages=20):
    """Locate `quote` inside a PDF and return the matching rectangles.

    Returns list[dict]: [{page, x0, y0, x1, y1, page_width, page_height}, ...].
    PNG/image sources return [] (PDF text-search doesn't apply).
    """
    if not pdf_path or not quote or not pdf_path.lower().endswith(".pdf"):
        return []
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return []
    needle = (quote or "").strip()
    if not needle:
        return []
    # PyMuPDF's search_for is line-based; long quotes spanning lines won't
    # match. Try a progressively shorter prefix.
    candidates = [needle]
    if len(needle) > 80:
        candidates += [needle[:80], needle[:50]]
    elif len(needle) > 50:
        candidates += [needle[:50]]
    candidates += [needle[:25]] if len(needle) > 25 else []
    rects = []
    try:
        doc = fitz.open(pdf_path)
        for pno in range(min(len(doc), max_pages)):
            page = doc[pno]
            for cand in candidates:
                hits = page.search_for(cand, quads=False)
                if hits:
                    pw, ph = page.rect.width, page.rect.height
                    for r in hits:
                        rects.append({
                            "page": pno + 1,
                            "x0": round(r.x0, 2), "y0": round(r.y0, 2),
                            "x1": round(r.x1, 2), "y1": round(r.y1, 2),
                            "page_width": round(pw, 2),
                            "page_height": round(ph, 2),
                        })
                    break  # stop trying shorter candidates if this one matched
            if rects:
                break  # stop scanning pages after first hit
        doc.close()
    except Exception:
        return []
    return rects


def add_citation(target_table, target_id, document_id, citation=None, field=None):
    """Persist a link from a derived fact (DB row) back to its source document.

    citation: optional dict from the extractor with keys page_or_section,
              field_or_chunk_id, quote_or_value. May be None when the fact
              came from a list[str] field with no per-item citation — we
              still record document_id + field so the trace exists.
    field:    fallback field_or_chunk_id when no citation dict is provided.

    Also computes a PDF bounding-box (best-effort) so the UI can render a
    visual highlight. Quietly skips when the source is a PNG/image or the
    quote can't be located.
    """
    if not document_id or not target_id:
        return
    c = citation or {}
    page = escape_sql(c.get('page_or_section') or '')
    fld = escape_sql(c.get('field_or_chunk_id') or field or '')
    quote = c.get('quote_or_value') or ''

    bboxes = _compute_bboxes(_document_source_path(document_id), quote)
    bbox_json = escape_sql(json.dumps(bboxes)) if bboxes else ''

    run_sql(
        f"INSERT INTO derived_fact_citations (target_table, target_id, document_id, "
        f"page_or_section, field_or_chunk_id, quote_or_value, bbox_json) "
        f"VALUES ('{escape_sql(target_table)}', {target_id}, {document_id}, "
        f"'{page}', '{fld}', '{escape_sql(quote)}', '{bbox_json}');"
    )


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


def populate_family_history(pid, family_history, document_id=None):
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
        row_id_out = run_sql(f"SELECT id FROM history_data WHERE pid={pid} LIMIT 1;")
        hist_id = int(row_id_out.strip().split('\n')[1]) if row_id_out and len(row_id_out.strip().split('\n')) > 1 else None
    else:
        cols = ", ".join(fields.keys())
        vals = ", ".join(f"'{escape_sql(' / '.join(v))}'" for v in fields.values())
        hist_id = run_sql_insert(f"INSERT INTO history_data (pid, uuid, date, {cols}) VALUES ({pid}, UNHEX(REPLACE(UUID(),'-','')), NOW(), {vals});")

    # One citation per family entry, tagged with the column it landed in.
    if hist_id and document_id:
        for entry in family_history:
            relation_raw = (entry.get('relation') or '').strip().lower()
            col = RELATION_TO_COLUMN.get(relation_raw, 'additional_history')
            add_citation('history_data', hist_id, document_id,
                         citation=entry.get('source_citation'),
                         field=col)
    print(f"  ✅ Family history populated ({len(family_history)} entries → {len(fields)} columns)")


def populate_emergency_contact(pid, ec_text, document_id=None):
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
    add_citation('patient_data', pid, document_id,
                 citation={'field_or_chunk_id': 'emergency_contact', 'quote_or_value': ec_text})
    print(f"  ✅ Emergency contact: {name_rel} / {phone}")


def populate_insurance(pid, ins_text, document_id=None):
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

    provider_text, policy = ins_text, ''
    m = re.search(r'(?:member\s*id|policy\s*(?:number|#)?|id\s*#?)\s*:?\s*([\w\-]+)', ins_text, re.IGNORECASE)
    if m:
        policy = m.group(1)
        provider_text = ins_text[:m.start()].strip(' -—:,')

    # OpenEMR's PHP-side InsuranceCompany class expects insurance_data.provider
    # to be an INTEGER FK into insurance_companies (it later passes that
    # value to PhoneNumberService::getPhonesByForeignId(int $foreignId)). If
    # we wrote the company name as a string, demographics.php throws a
    # TypeError. Resolve (or upsert) the company row first and store its
    # integer id.
    company_id = _upsert_insurance_company(provider_text)

    run_sql(
        f"DELETE FROM insurance_data WHERE pid={pid} AND type='primary';"
    )
    ins_id = run_sql_insert(
        f"INSERT INTO insurance_data (pid, type, provider, plan_name, policy_number, date) "
        f"VALUES ({pid}, 'primary', '{company_id}', '{escape_sql(provider_text)}', "
        f"'{escape_sql(policy)}', CURDATE());"
    )
    add_citation('insurance_data', ins_id, document_id,
                 citation={'field_or_chunk_id': 'insurance', 'quote_or_value': ins_text})
    print(f"  ✅ Insurance: {provider_text} (company_id={company_id}) / policy={policy}")


def _upsert_insurance_company(name: str) -> int:
    """Return the integer id of an insurance_companies row with the given
    name, inserting one (with a fresh uuid) if no match exists. The row is
    minimal — only id/uuid/name/inactive — but that's enough to satisfy the
    PHP-side InsuranceCompany class and OpenEMR's FHIR Coverage projection.
    """
    name = (name or '').strip() or 'Unknown carrier'
    out = run_sql(
        f"SELECT id FROM insurance_companies WHERE name='{escape_sql(name)}' LIMIT 1;"
    ) or ""
    lines = [l for l in out.strip().split("\n") if l]
    if len(lines) >= 2 and lines[1].strip().isdigit():
        return int(lines[1].strip())
    next_id_out = run_sql("SELECT COALESCE(MAX(id),0)+1 FROM insurance_companies;") or ""
    nlines = [l for l in next_id_out.strip().split("\n") if l]
    next_id = int(nlines[1].strip()) if len(nlines) >= 2 else 1
    run_sql_insert(
        "INSERT INTO insurance_companies (id, uuid, name, inactive) VALUES "
        f"({next_id}, UNHEX(REPLACE(UUID(),'-','')), '{escape_sql(name)}', 0);"
    )
    return next_id


def populate_problem_list(pid, conditions, form_date, document_id=None):
    """Insert each condition as a lists row (type='medical_problem')."""
    if not conditions:
        return
    for cond in conditions:
        cond = str(cond).strip()
        if not cond:
            continue
        existing = run_sql(
            f"SELECT id FROM lists WHERE pid={pid} AND type='medical_problem' AND title='{escape_sql(cond)}' LIMIT 1;"
        )
        if existing and len(existing.strip().split('\n')) > 1:
            continue
        new_id = run_sql_insert(
            f"INSERT INTO lists (pid, type, title, begdate, activity) "
            f"VALUES ({pid}, 'medical_problem', '{escape_sql(cond)}', '{form_date}', 1);"
        )
        add_citation('lists', new_id, document_id,
                     citation={'field_or_chunk_id': 'past_medical_history', 'quote_or_value': cond})
    print(f"  ✅ Past medical history: {len(conditions)} entries")


def populate_surgical_history(pid, surgeries, form_date, document_id=None):
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
        new_id = run_sql_insert(
            f"INSERT INTO lists (pid, type, title, begdate, activity) "
            f"VALUES ({pid}, 'surgery', '{escape_sql(surg)}', '{form_date}', 1);"
        )
        add_citation('lists', new_id, document_id,
                     citation={'field_or_chunk_id': 'surgical_history', 'quote_or_value': surg})
    print(f"  ✅ Surgical history: {len(surgeries)} entries")


def populate_treating_physicians(pid, physicians_text, document_id=None):
    """Save treating physicians free-text into patient_data.care_team_provider."""
    if not physicians_text:
        return
    run_sql(
        f"UPDATE patient_data SET care_team_provider='{escape_sql(physicians_text)}' WHERE pid={pid};"
    )
    add_citation('patient_data', pid, document_id,
                 citation={'field_or_chunk_id': 'treating_physicians', 'quote_or_value': physicians_text})
    print(f"  ✅ Treating physicians: {physicians_text[:80]}")


def populate_social_history(pid, social_history_text, document_id=None):
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
        hist_id = int(existing.strip().split('\n')[1])
    else:
        cols = ", ".join(fields.keys())
        vals = ", ".join(f"'{escape_sql(v)}'" for v in fields.values())
        hist_id = run_sql_insert(f"INSERT INTO history_data (pid, uuid, date, {cols}) VALUES ({pid}, UNHEX(REPLACE(UUID(),'-','')), NOW(), {vals});")
    if hist_id and document_id:
        add_citation('history_data', hist_id, document_id,
                     citation={'field_or_chunk_id': 'social_history', 'quote_or_value': blob[:500]})
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
    mrn = escape_sql((data.get('patient_mrn') or '').strip())

    print(f"\n{'='*60}")
    print(f"  Ingesting: {fname} {lname} (pid={pid})")
    print(f"  DOB: {dob} | Sex: {sex}")
    print(f"  Chief concern: {data.get('chief_concern', 'N/A')[:80]}")
    print(f"{'='*60}")

    # 1. Create patient.  pubpid is OpenEMR's external public ID and the
    # field that drives FHIR Patient.identifier — populate from the MRN
    # printed on the intake form when present.
    sql = (
        f"INSERT INTO patient_data (pid, fname, lname, DOB, sex, phone_home, street, city, state, postal_code, pubpid) "
        f"VALUES ({pid}, '{escape_sql(fname)}', '{escape_sql(lname)}', '{dob}', '{sex}', '{phone}', "
        f"'{escape_sql(street)}', '{escape_sql(city)}', '{escape_sql(state)}', '{escape_sql(postal)}', '{mrn}');"
    )
    run_sql(sql)
    print(f"  ✅ Patient created: {fname} {lname} (pid={pid}, MRN={mrn or '—'})")

    # Generate UUID
    run_sql(f"UPDATE patient_data SET uuid = UNHEX(REPLACE(UUID(), '-', '')) WHERE pid = {pid} AND uuid IS NULL;")

    form_date = data.get('form_date', '2026-04-20')

    # 2. Store source document FIRST so derived facts can cite it.
    document_id = store_document(pid, source_path, form_date, category_id=4)
    print(f"  ✅ Source document reference stored in OpenEMR (doc_id={document_id})")

    # 3. Medications
    meds = data.get('current_medications', [])
    for med in meds:
        med_name = escape_sql(med.get('medication_name', ''))
        dose = escape_sql(med.get('dose', ''))
        freq = escape_sql(med.get('frequency', ''))
        full_drug = f"{med_name} {dose}".strip()
        rx_id = run_sql_insert(
            f"INSERT INTO prescriptions (patient_id, drug, dosage, date_added, active, txDate, "
            f"usage_category_title, request_intent_title) "
            f"VALUES ({pid}, '{escape_sql(full_drug)}', '{escape_sql(freq)}', NOW(), 1, CURDATE(), '', '');"
        )
        add_citation('prescriptions', rx_id, document_id,
                     citation=med.get('source_citation'),
                     field='current_medications')
    print(f"  ✅ {len(meds)} medications added")

    # 4. Allergies
    allergies = data.get('allergies', [])
    for allergy in allergies:
        allergen = escape_sql(allergy.get('allergen', ''))
        reaction = escape_sql(allergy.get('reaction', ''))
        al_id = run_sql_insert(
            f"INSERT INTO lists (pid, type, title, diagnosis, begdate, activity) "
            f"VALUES ({pid}, 'allergy', '{allergen} ({reaction})', '', CURDATE(), 1);"
        )
        add_citation('lists', al_id, document_id,
                     citation=allergy.get('source_citation'),
                     field='allergies')
    print(f"  ✅ {len(allergies)} allergies added")

    # 5. Encounter with chief concern
    chief_concern = escape_sql(data.get('chief_concern', 'New patient visit'))
    encounter_num = next_encounter_number()
    fe_id = run_sql_insert(
        f"INSERT INTO form_encounter (pid, encounter, date, reason, facility_id, provider_id) "
        f"VALUES ({pid}, {encounter_num}, '{form_date}', '{chief_concern}', 3, 1);"
    )
    run_sql(
        f"INSERT INTO forms (date, encounter, form_name, form_id, pid, formdir, provider_id, deleted) "
        f"VALUES ('{form_date}', {encounter_num}, 'New Patient Encounter', {fe_id}, {pid}, 'newpatient', 1, 0);"
    )
    add_citation('form_encounter', fe_id, document_id,
                 citation={'field_or_chunk_id': 'chief_concern', 'quote_or_value': data.get('chief_concern', '')})
    print(f"  ✅ Encounter #{encounter_num} added: {data.get('chief_concern', '')[:60]}")

    # 6. Family + social history
    populate_family_history(pid, data.get('family_history', []), document_id=document_id)
    populate_social_history(pid, data.get('social_history'), document_id=document_id)

    # 7. Past medical + surgical history
    populate_problem_list(pid, data.get('past_medical_history', []), form_date, document_id=document_id)
    populate_surgical_history(pid, data.get('surgical_history', []), form_date, document_id=document_id)

    # 8. Emergency contact, insurance, treating physicians
    populate_emergency_contact(pid, data.get('emergency_contact'), document_id=document_id)
    populate_insurance(pid, data.get('insurance'), document_id=document_id)
    populate_treating_physicians(pid, data.get('treating_physicians'), document_id=document_id)

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

    # 1. Store source document FIRST so derived facts can cite it.
    document_id = store_document(patient_pid, source_path, collection_date, category_id=2)
    print(f"  ✅ Lab document reference stored for pid={patient_pid} (doc_id={document_id})")

    # 2. Create procedure_order with specimen info
    spec_type = escape_sql(data.get('specimen_type') or '')
    spec_vol = escape_sql(data.get('specimen_volume') or '')
    order_id = run_sql_insert(
        f"INSERT INTO procedure_order (uuid, provider_id, patient_id, encounter_id, date_collected, date_ordered, "
        f"order_priority, order_status, activity, specimen_type, specimen_volume) "
        f"VALUES (UNHEX(REPLACE(UUID(),'-','')), 1, {patient_pid}, {encounter_id}, '{collection_date}', '{collection_date}', "
        f"'normal', 'complete', 1, '{spec_type}', '{spec_vol}');"
    )
    if not order_id:
        print(f"  ❌ Failed to create procedure_order")
        return
    add_citation('procedure_order', order_id, document_id,
                 citation={'field_or_chunk_id': 'specimen', 'quote_or_value': f"{data.get('specimen_type','')} / {data.get('specimen_volume','')}"})

    # 3. Create procedure_report. Prepend specimen_notes (if any) so they show
    # alongside the interpretation in the chart's report-notes panel.
    spec_notes = (data.get('specimen_notes') or '').strip()
    interp_text = (data.get('interpretive_comments') or '').strip()
    combined = "\n\n".join(p for p in [
        f"Specimen notes: {spec_notes}" if spec_notes else "",
        interp_text,
    ] if p)
    interp = escape_sql(combined)
    report_id = run_sql_insert(
        f"INSERT INTO procedure_report (uuid, procedure_order_id, procedure_order_seq, date_collected, date_report, report_status, review_status, report_notes) "
        f"VALUES (UNHEX(REPLACE(UUID(),'-','')), {order_id}, 1, '{collection_date}', '{collection_date}', 'final', 'received', '{interp}');"
    )
    if not report_id:
        print(f"  ❌ Failed to create procedure_report")
        return
    if combined:
        add_citation('procedure_report', report_id, document_id,
                     citation={'field_or_chunk_id': 'interpretive_comments', 'quote_or_value': combined[:500]})

    # 4. Insert each lab result
    for lab in labs:
        test_name = escape_sql(lab.get('test_name', ''))
        value = escape_sql(lab.get('value', ''))
        unit = escape_sql(lab.get('unit', ''))
        ref_range = escape_sql(lab.get('reference_range', ''))
        flag = escape_sql(lab.get('abnormal_flag', '') or '')

        result_id = run_sql_insert(
            f"INSERT INTO procedure_result (uuid, procedure_report_id, result_data_type, result_code, result_text, "
            f"date, units, result, `range`, abnormal, result_status) "
            f"VALUES (UNHEX(REPLACE(UUID(),'-','')), {report_id}, 'S', '', '{test_name}', '{collection_date}', "
            f"'{unit}', '{value}', '{ref_range}', '{flag}', 'final');"
        )
        add_citation('procedure_result', result_id, document_id,
                     citation=lab.get('source_citation'),
                     field=f"lab_results[{lab.get('test_name','')}]")

        flag_display = f"⚠️ {flag}" if flag else "✓"
        print(f"    📊 {test_name}: {value} {unit} {flag_display}")

    print(f"  ✅ {len(labs)} lab results stored in procedure tables (order={order_id}, report={report_id})")


def ensure_schema():
    """Idempotent schema fixes for fresh OpenEMR installs.

    OpenEMR's stock images ship with two known issues that block this
    pipeline if not addressed: `documents.id` lacks AUTO_INCREMENT (so
    every insert past the first lands at id=0 and silently collides on
    the primary key), and the `derived_fact_citations` sidecar table
    used by the citation pipeline doesn't exist at all. Both are safe
    to apply repeatedly — running this function at the top of `main()`
    means a fresh deploy or CI run never has to run SQL by hand.
    """
    # 1. AUTO_INCREMENT on documents.id. MODIFY is a no-op when the
    #    column is already auto-increment, so re-runs are harmless.
    run_sql("ALTER TABLE documents MODIFY id INT(11) NOT NULL AUTO_INCREMENT;")

    # 2. derived_fact_citations sidecar.
    run_sql(
        "CREATE TABLE IF NOT EXISTS derived_fact_citations ("
        "  id BIGINT AUTO_INCREMENT PRIMARY KEY,"
        "  target_table VARCHAR(64) NOT NULL,"
        "  target_id BIGINT NOT NULL,"
        "  document_id BIGINT NOT NULL,"
        "  page_or_section VARCHAR(255),"
        "  field_or_chunk_id VARCHAR(255),"
        "  quote_or_value TEXT,"
        "  bbox_json TEXT,"
        "  KEY idx_target (target_table, target_id),"
        "  KEY idx_document (document_id)"
        ");"
    )


def main():
    print("=" * 60)
    print("  OpenEMR Document Ingestion Pipeline")
    print("  Extract → Validate → Store")
    print("=" * 60)

    # Apply schema migrations before any inserts. Self-heals on every run.
    ensure_schema()

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
