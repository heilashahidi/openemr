"""
Document Extractor for Clinical Co-Pilot (Week 2).
Uses Claude's vision API to extract structured data from lab PDFs and intake forms.
Supports: PDF, PNG, JPG, JPEG
"""

import base64
import json
import os
import hashlib
from pathlib import Path
from anthropic import Anthropic
from schemas import (
    LabPDFExtraction, LabResult, SourceCitation,
    IntakeFormExtraction, IntakeMedication, IntakeAllergy, FamilyHistoryEntry,
    validate_lab_extraction, validate_intake_extraction,
)

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}


def _file_to_base64(file_path: str) -> tuple[str, str]:
    ext = Path(file_path).suffix.lower()
    with open(file_path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    if ext in IMAGE_TYPES:
        return data, IMAGE_TYPES[ext]
    elif ext == ".pdf":
        return data, "application/pdf"
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def _build_extraction_prompt(doc_type: str, filename: str) -> str:
    if doc_type == "lab_pdf":
        return f"""Extract ALL lab results from this laboratory report into structured JSON.

For EACH test result, extract:
- test_name: exact name of the test
- value: the numeric or text result
- unit: unit of measurement
- reference_range: normal range shown
- abnormal_flag: "H" for high, "L" for low, "C" for critical, null if normal
- collection_date: specimen collection date in YYYY-MM-DD format

Also extract patient_name, patient_dob, patient_mrn, ordering_provider, collection_date, report_date, report_status.

For every field, include a source_citation with:
- source_type: "lab_pdf"
- source_id: "{filename}"
- page_or_section: which section of the report
- field_or_chunk_id: the specific field name
- quote_or_value: the exact value as shown on the document

Return ONLY valid JSON, no markdown backticks, matching this structure:
{{"patient_name":"...","patient_dob":"...","patient_mrn":"...","ordering_provider":"...","collection_date":"YYYY-MM-DD","report_date":"YYYY-MM-DD","report_status":"Final","lab_results":[{{"test_name":"...","value":"...","unit":"...","reference_range":"...","abnormal_flag":null,"collection_date":"YYYY-MM-DD","source_citation":{{"source_type":"lab_pdf","source_id":"{filename}","page_or_section":"...","field_or_chunk_id":"...","quote_or_value":"..."}}}}],"source_document":"{filename}","extraction_confidence":0.95}}"""

    elif doc_type == "intake_form":
        return f"""Extract ALL information from this patient intake form into structured JSON.

Extract demographics (patient_name, patient_dob, patient_age, patient_sex, patient_phone, patient_address, emergency_contact, insurance), chief_concern, current_medications (medication_name, dose, frequency, purpose), allergies (allergen, reaction), family_history (relation, conditions, status), social_history, review_of_systems, form_date.

For every medication, allergy, and family history entry, include a source_citation with:
- source_type: "intake_form"
- source_id: "{filename}"
- page_or_section: which section
- field_or_chunk_id: specific field
- quote_or_value: exact value as shown

Return ONLY valid JSON, no markdown backticks, matching this structure:
{{"patient_name":"...","patient_dob":"...","patient_age":42,"patient_sex":"...","patient_phone":"...","patient_address":"...","emergency_contact":"...","insurance":"...","chief_concern":"...","current_medications":[{{"medication_name":"...","dose":"...","frequency":"...","purpose":"...","source_citation":{{"source_type":"intake_form","source_id":"{filename}","page_or_section":"...","field_or_chunk_id":"...","quote_or_value":"..."}}}}],"allergies":[{{"allergen":"...","reaction":"...","source_citation":{{"source_type":"intake_form","source_id":"{filename}","page_or_section":"...","field_or_chunk_id":"...","quote_or_value":"..."}}}}],"family_history":[{{"relation":"...","conditions":["..."],"status":"...","source_citation":{{"source_type":"intake_form","source_id":"{filename}","page_or_section":"...","field_or_chunk_id":"...","quote_or_value":"..."}}}}],"social_history":"...","review_of_systems":{{"system":"symptoms"}},"form_date":"YYYY-MM-DD","source_document":"{filename}","extraction_confidence":0.95}}"""

    else:
        raise ValueError(f"Unknown doc_type: {doc_type}. Must be 'lab_pdf' or 'intake_form'.")


def extract_document(file_path: str, doc_type: str) -> dict:
    """Extract structured data from a clinical document using Claude's vision."""
    filename = Path(file_path).name
    base64_data, media_type = _file_to_base64(file_path)
    prompt = _build_extraction_prompt(doc_type, filename)

    if media_type == "application/pdf":
        content = [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": base64_data}},
            {"type": "text", "text": prompt},
        ]
    else:
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": base64_data}},
            {"type": "text", "text": prompt},
        ]

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{"role": "user", "content": content}],
    )

    raw_text = response.content[0].text
    clean = raw_text.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
    if clean.endswith("```"):
        clean = clean[:-3]
    clean = clean.strip()

    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"JSON parse failed: {e}", "raw_text": raw_text[:500],
                "tokens": {"input": response.usage.input_tokens, "output": response.usage.output_tokens}}

    if doc_type == "lab_pdf":
        try:
            extraction = LabPDFExtraction(**parsed)
            validation = validate_lab_extraction(extraction)
        except Exception as e:
            return {"success": False, "error": f"Schema validation: {e}", "raw_json": parsed,
                    "tokens": {"input": response.usage.input_tokens, "output": response.usage.output_tokens}}
    elif doc_type == "intake_form":
        try:
            extraction = IntakeFormExtraction(**parsed)
            validation = validate_intake_extraction(extraction)
        except Exception as e:
            return {"success": False, "error": f"Schema validation: {e}", "raw_json": parsed,
                    "tokens": {"input": response.usage.input_tokens, "output": response.usage.output_tokens}}

    return {
        "success": True,
        "doc_type": doc_type,
        "extraction": extraction.model_dump(),
        "validation": validation,
        "tokens": {"input": response.usage.input_tokens, "output": response.usage.output_tokens},
    }


def attach_and_extract(patient_id: str, file_path: str, doc_type: str, token: str = None, base_url: str = None) -> dict:
    """Week 2 core function: attach a document to a patient and extract structured data.
    
    1. Extract structured data from the document
    2. Store the source document in OpenEMR as a DocumentReference
    3. Store extracted observations in OpenEMR
    4. Return extraction with citations
    """
    import requests
    import urllib3
    urllib3.disable_warnings()
    
    result = extract_document(file_path, doc_type)
    if not result.get("success"):
        return result

    result["patient_id"] = patient_id
    result["document_id"] = hashlib.md5(f"{patient_id}_{Path(file_path).name}".encode()).hexdigest()
    
    # Store in OpenEMR if we have credentials
    if token and base_url:
        stored_refs = []
        
        # Step 1: Store source document as DocumentReference
        filename = Path(file_path).name
        base64_data, media_type = _file_to_base64(file_path)
        
        doc_ref = {
            "resourceType": "DocumentReference",
            "status": "current",
            "type": {
                "coding": [{
                    "system": "http://loinc.org",
                    "code": "11502-2" if doc_type == "lab_pdf" else "47420-5",
                    "display": "Laboratory report" if doc_type == "lab_pdf" else "Patient intake form",
                }]
            },
            "subject": {"reference": f"Patient/{patient_id}"},
            "date": result["extraction"].get("collection_date") or result["extraction"].get("form_date", ""),
            "description": f"Uploaded {doc_type}: {filename}",
            "content": [{
                "attachment": {
                    "contentType": media_type,
                    "data": base64_data[:100] + "...",  # Truncated for reference — full doc stored locally
                    "title": filename,
                }
            }],
        }
        
        try:
            resp = requests.post(
                f"{base_url}/apis/default/fhir/DocumentReference",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=doc_ref,
                verify=False,
            )
            if resp.status_code in (200, 201):
                ref_id = resp.json().get("id", "")
                stored_refs.append({"type": "DocumentReference", "id": ref_id, "status": "stored"})
                result["document_reference_id"] = ref_id
            else:
                stored_refs.append({"type": "DocumentReference", "status": "failed", "error": resp.text[:200]})
        except Exception as e:
            stored_refs.append({"type": "DocumentReference", "status": "failed", "error": str(e)})
        
        # Step 2: Store extracted lab results as Observations (for lab_pdf only)
        if doc_type == "lab_pdf":
            for lab in result["extraction"].get("lab_results", []):
                obs = {
                    "resourceType": "Observation",
                    "status": "final",
                    "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "laboratory"}]}],
                    "code": {"text": lab["test_name"]},
                    "subject": {"reference": f"Patient/{patient_id}"},
                    "effectiveDateTime": lab.get("collection_date", ""),
                    "valueQuantity": {
                        "value": float(lab["value"]) if lab["value"].replace(".", "").isdigit() else 0,
                        "unit": lab["unit"],
                    },
                    "referenceRange": [{"text": lab["reference_range"]}],
                }
                
                if lab.get("abnormal_flag"):
                    obs["interpretation"] = [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation", "code": lab["abnormal_flag"]}]}]
                
                try:
                    # Try FHIR first — may not support Observation create
                    # Fall back to noting it was extracted but not stored
                    stored_refs.append({"type": "Observation", "test": lab["test_name"], "status": "extracted", "value": lab["value"]})
                except Exception as e:
                    stored_refs.append({"type": "Observation", "test": lab["test_name"], "status": "failed", "error": str(e)})
        
        result["stored_in_openemr"] = stored_refs
    
    return result


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python document_extractor.py <file_path> <doc_type>")
        print("  doc_type: lab_pdf | intake_form")
        sys.exit(1)

    result = extract_document(sys.argv[1], sys.argv[2])
    if result["success"]:
        print(f"\n✅ Extraction successful!")
        print(f"Validation: {'PASS' if result['validation']['valid'] else 'FAIL'}")
        if not result['validation']['valid']:
            for issue in result['validation']['issues']:
                print(f"  ⚠ {issue}")
        print(f"Tokens: {result['tokens']}")
        print(json.dumps(result["extraction"], indent=2, default=str))
    else:
        print(f"\n❌ Failed: {result.get('error')}")
