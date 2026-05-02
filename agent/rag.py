"""
RAG module for Clinical Co-Pilot.
Indexes encounter notes from OpenEMR FHIR API into ChromaDB
and provides semantic search over clinical notes.
"""

import requests
import urllib3
import chromadb
import json
import hashlib

urllib3.disable_warnings()

# In-memory ChromaDB
client = chromadb.Client()
collection = None
_indexed_patients = set()


def init_collection():
    """Initialize or get the notes collection."""
    global collection
    try:
        collection = client.get_collection("clinical_notes")
    except:
        collection = client.create_collection(
            name="clinical_notes",
            metadata={"description": "Clinical encounter notes from OpenEMR"}
        )
    return collection


def _get_encounter_notes(patient_id, token, base_url):
    """Fetch all encounters with their reasons/notes for a patient."""
    resp = requests.get(
        f"{base_url}/apis/default/fhir/Encounter",
        headers={"Authorization": f"Bearer {token}"},
        params={"patient": patient_id, "_sort": "-date", "_count": "50"},
        verify=False,
    )
    if resp.status_code != 200:
        return []

    bundle = resp.json()
    if "entry" not in bundle:
        return []

    notes = []
    for entry in bundle["entry"]:
        resource = entry.get("resource", {})
        encounter_id = resource.get("id", "")
        period = resource.get("period", {})
        date = period.get("start", "Unknown date")

        # Extract reason text
        reason_list = resource.get("reasonCode", [])
        reason = reason_list[0].get("text", "") if reason_list else ""

        # Extract type text
        type_list = resource.get("type", [])
        visit_type = type_list[0].get("text", "") if type_list else ""

        # Build note text from available fields
        note_parts = []
        if date:
            note_parts.append(f"Visit date: {date}")
        if visit_type:
            note_parts.append(f"Visit type: {visit_type}")
        if reason:
            note_parts.append(f"Reason for visit: {reason}")

        note_text = ". ".join(note_parts)
        if note_text:
            notes.append({
                "text": note_text,
                "encounter_id": encounter_id,
                "date": date,
                "reason": reason,
                "patient_id": patient_id,
            })

    return notes


def _get_conditions_as_notes(patient_id, token, base_url):
    """Fetch conditions and format as searchable notes."""
    resp = requests.get(
        f"{base_url}/apis/default/fhir/Condition",
        headers={"Authorization": f"Bearer {token}"},
        params={"patient": patient_id},
        verify=False,
    )
    if resp.status_code != 200:
        return []

    bundle = resp.json()
    if "entry" not in bundle:
        return []

    notes = []
    for entry in bundle["entry"]:
        resource = entry.get("resource", {})
        condition_id = resource.get("id", "")
        code = resource.get("code", {})
        text = code.get("text", "Unknown condition")
        coding = code.get("coding", [{}])[0]
        icd_code = coding.get("code", "")
        onset = resource.get("onsetDateTime", "Unknown")
        status = resource.get("clinicalStatus", {}).get("coding", [{}])[0].get("code", "")

        note_text = f"Diagnosis: {text}. ICD code: {icd_code}. Onset: {onset}. Status: {status}."
        notes.append({
            "text": note_text,
            "encounter_id": condition_id,
            "date": onset,
            "reason": f"Condition: {text}",
            "patient_id": patient_id,
        })

    return notes


def _get_medications_as_notes(patient_id, token, base_url):
    """Fetch medications and format as searchable notes."""
    resp = requests.get(
        f"{base_url}/apis/default/fhir/MedicationRequest",
        headers={"Authorization": f"Bearer {token}"},
        params={"patient": patient_id, "status": "active"},
        verify=False,
    )
    if resp.status_code != 200:
        return []

    bundle = resp.json()
    if "entry" not in bundle:
        return []

    notes = []
    for entry in bundle["entry"]:
        resource = entry.get("resource", {})
        med_id = resource.get("id", "")
        med_code = resource.get("medicationCodeableConcept", {})
        med_name = med_code.get("text", "Unknown medication")
        dosage_list = resource.get("dosageInstruction", [])
        dosage = dosage_list[0].get("text", "") if dosage_list else ""
        authored = resource.get("authoredOn", "Unknown")

        note_text = f"Medication prescribed: {med_name}. Dosage: {dosage}. Started: {authored}."
        notes.append({
            "text": note_text,
            "encounter_id": med_id,
            "date": authored,
            "reason": f"Medication: {med_name}",
            "patient_id": patient_id,
        })

    return notes


def index_patient(patient_id, token, base_url):
    """Index all available notes for a patient into ChromaDB."""
    global collection
    if collection is None:
        init_collection()

    if patient_id in _indexed_patients:
        return

    # Gather notes from multiple sources
    all_notes = []
    all_notes.extend(_get_encounter_notes(patient_id, token, base_url))
    all_notes.extend(_get_conditions_as_notes(patient_id, token, base_url))
    all_notes.extend(_get_medications_as_notes(patient_id, token, base_url))

    if not all_notes:
        _indexed_patients.add(patient_id)
        return

    # Add to ChromaDB
    ids = []
    documents = []
    metadatas = []

    for note in all_notes:
        doc_id = hashlib.md5(f"{note['patient_id']}_{note['encounter_id']}_{note['text'][:50]}".encode()).hexdigest()
        ids.append(doc_id)
        documents.append(note["text"])
        metadatas.append({
            "patient_id": note["patient_id"],
            "encounter_id": note["encounter_id"],
            "date": note["date"],
            "reason": note["reason"],
        })

    collection.add(ids=ids, documents=documents, metadatas=metadatas)
    _indexed_patients.add(patient_id)
    print(f"  RAG: Indexed {len(all_notes)} notes for patient {patient_id[:8]}...")


def search_notes(patient_id, query, token, base_url, n_results=5):
    """Search indexed notes for a patient. Returns relevant chunks with citations."""
    # Ensure patient is indexed
    index_patient(patient_id, token, base_url)

    if collection is None or collection.count() == 0:
        return {
            "success": True,
            "data": "No clinical notes indexed for this patient.",
            "citations": [],
        }

    # Query with mandatory patient_id filter
    results = collection.query(
        query_texts=[query],
        n_results=n_results,
        where={"patient_id": patient_id},
    )

    if not results["documents"][0]:
        return {
            "success": True,
            "data": "No relevant notes found in the patient's record for this query.",
            "citations": [],
        }

    # Format results
    found_notes = []
    citations = []
    for i, doc in enumerate(results["documents"][0]):
        meta = results["metadatas"][0][i]
        distance = results["distances"][0][i] if results.get("distances") else None
        found_notes.append({
            "text": doc,
            "date": meta.get("date", "Unknown"),
            "encounter_id": meta.get("encounter_id", ""),
            "relevance": round(1 - distance, 3) if distance else None,
        })
        citations.append({
            "resource": "Encounter",
            "id": meta.get("encounter_id", ""),
            "url": f"Encounter/{meta.get('encounter_id', '')}",
        })

    return {
        "success": True,
        "data": found_notes,
        "citations": citations,
    }
