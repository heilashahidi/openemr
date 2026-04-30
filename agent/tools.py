"""
FHIR Tools for the Clinical Co-Pilot.
Each tool wraps a specific FHIR API call against OpenEMR.
"""

import requests
import urllib3

urllib3.disable_warnings()


TOOLS = [
    {
        "name": "get_patient_summary",
        "description": "Get patient demographics: name, DOB, sex, address, phone.",
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string", "description": "Patient UUID"}
            },
            "required": ["patient_id"],
        },
    },
    {
        "name": "get_active_conditions",
        "description": "Get the patient's active problem list — chronic conditions and ongoing diagnoses.",
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string", "description": "Patient UUID"}
            },
            "required": ["patient_id"],
        },
    },
    {
        "name": "get_active_medications",
        "description": "Get the patient's current active medications with dosages.",
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string", "description": "Patient UUID"}
            },
            "required": ["patient_id"],
        },
    },
    {
        "name": "get_allergies",
        "description": "Get the patient's allergy list.",
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string", "description": "Patient UUID"}
            },
            "required": ["patient_id"],
        },
    },
    {
        "name": "get_recent_encounters",
        "description": "Get the patient's recent encounters/visits including visit reasons. Returns the most recent 5.",
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string", "description": "Patient UUID"}
            },
            "required": ["patient_id"],
        },
    },
    {
        "name": "get_recent_labs",
        "description": "Get the patient's recent laboratory results. Returns the most recent 10.",
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string", "description": "Patient UUID"}
            },
            "required": ["patient_id"],
        },
    },
]


def _fhir_get(path, token, base_url, params=None):
    """Make a GET request to the FHIR API."""
    url = f"{base_url}/apis/default/fhir/{path}"
    resp = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        verify=False,
    )
    if resp.status_code == 200:
        return resp.json()
    else:
        return {"error": f"FHIR API returned {resp.status_code}", "detail": resp.text[:200]}


def _extract_bundle(bundle):
    """Extract resources from a FHIR Bundle."""
    if "entry" not in bundle:
        return []
    return [entry.get("resource", {}) for entry in bundle["entry"]]


def get_patient_summary(patient_id, token, base_url):
    data = _fhir_get(f"Patient/{patient_id}", token, base_url)
    if "error" in data:
        return {"success": False, "error": data["error"], "citations": []}

    name = data.get("name", [{}])[0]
    return {
        "success": True,
        "data": {
            "name": f"{' '.join(name.get('given', []))} {name.get('family', '')}",
            "dob": data.get("birthDate", "Unknown"),
            "sex": data.get("gender", "Unknown"),
            "id": data.get("id", ""),
        },
        "citations": [{"resource": "Patient", "id": data.get("id", ""), "url": f"Patient/{data.get('id', '')}"}],
    }


def get_active_conditions(patient_id, token, base_url):
    data = _fhir_get("Condition", token, base_url, params={"patient": patient_id})
    if "error" in data:
        return {"success": False, "error": data["error"], "citations": []}

    resources = _extract_bundle(data)
    conditions = []
    citations = []
    for r in resources:
        code = r.get("code", {})
        text = code.get("text", "Unknown")
        coding = code.get("coding", [{}])[0]
        condition = {
            "name": text,
            "code": coding.get("code", ""),
            "system": coding.get("system", ""),
            "onset": r.get("onsetDateTime", "Unknown"),
            "status": r.get("clinicalStatus", {}).get("coding", [{}])[0].get("code", "unknown"),
            "id": r.get("id", ""),
        }
        conditions.append(condition)
        citations.append({"resource": "Condition", "id": r.get("id", ""), "url": f"Condition/{r.get('id', '')}"})

    return {"success": True, "data": conditions if conditions else "No conditions documented.", "citations": citations}


def get_active_medications(patient_id, token, base_url):
    data = _fhir_get("MedicationRequest", token, base_url, params={"patient": patient_id, "status": "active"})
    if "error" in data:
        return {"success": False, "error": data["error"], "citations": []}

    resources = _extract_bundle(data)
    meds = []
    citations = []
    for r in resources:
        med_code = r.get("medicationCodeableConcept", {})
        text = med_code.get("text", "Unknown medication")
        dosage_list = r.get("dosageInstruction", [])
        dosage = dosage_list[0].get("text", "") if dosage_list else ""
        med = {
            "name": text,
            "dosage": dosage,
            "status": r.get("status", ""),
            "authored": r.get("authoredOn", ""),
            "id": r.get("id", ""),
        }
        meds.append(med)
        citations.append({"resource": "MedicationRequest", "id": r.get("id", ""), "url": f"MedicationRequest/{r.get('id', '')}"})

    return {"success": True, "data": meds if meds else "No active medications documented.", "citations": citations}


def get_allergies(patient_id, token, base_url):
    data = _fhir_get("AllergyIntolerance", token, base_url, params={"patient": patient_id})
    if "error" in data:
        return {"success": False, "error": data["error"], "citations": []}

    resources = _extract_bundle(data)
    allergies = []
    citations = []
    for r in resources:
        code = r.get("code", {})
        text = code.get("text", "Unknown")
        allergy = {
            "substance": text,
            "status": r.get("clinicalStatus", {}).get("coding", [{}])[0].get("code", "unknown"),
            "id": r.get("id", ""),
        }
        allergies.append(allergy)
        citations.append({"resource": "AllergyIntolerance", "id": r.get("id", ""), "url": f"AllergyIntolerance/{r.get('id', '')}"})

    return {"success": True, "data": allergies if allergies else "No allergies documented.", "citations": citations}


def get_recent_encounters(patient_id, token, base_url):
    data = _fhir_get("Encounter", token, base_url, params={"patient": patient_id, "_sort": "-date", "_count": "5"})
    if "error" in data:
        return {"success": False, "error": data["error"], "citations": []}

    resources = _extract_bundle(data)
    encounters = []
    citations = []
    for r in resources:
        reason_list = r.get("reasonCode", [])
        reason = reason_list[0].get("text", "No reason recorded") if reason_list else "No reason recorded"
        period = r.get("period", {})
        encounter = {
            "date": period.get("start", "Unknown"),
            "reason": reason,
            "status": r.get("status", ""),
            "type": r.get("type", [{}])[0].get("text", "") if r.get("type") else "",
            "id": r.get("id", ""),
        }
        encounters.append(encounter)
        citations.append({"resource": "Encounter", "id": r.get("id", ""), "url": f"Encounter/{r.get('id', '')}"})

    return {"success": True, "data": encounters if encounters else "No encounters documented.", "citations": citations}


def get_recent_labs(patient_id, token, base_url):
    data = _fhir_get(
        "Observation",
        token,
        base_url,
        params={"patient": patient_id, "category": "laboratory", "_sort": "-date", "_count": "10"},
    )
    if "error" in data:
        return {"success": False, "error": data["error"], "citations": []}

    resources = _extract_bundle(data)
    labs = []
    citations = []
    for r in resources:
        code = r.get("code", {})
        value = r.get("valueQuantity", {})
        lab = {
            "name": code.get("text", "Unknown"),
            "value": value.get("value", ""),
            "unit": value.get("unit", ""),
            "date": r.get("effectiveDateTime", "Unknown"),
            "status": r.get("status", ""),
            "id": r.get("id", ""),
        }
        labs.append(lab)
        citations.append({"resource": "Observation", "id": r.get("id", ""), "url": f"Observation/{r.get('id', '')}"})

    return {"success": True, "data": labs if labs else "No laboratory results documented.", "citations": citations}


# Tool dispatcher
TOOL_FUNCTIONS = {
    "get_patient_summary": get_patient_summary,
    "get_active_conditions": get_active_conditions,
    "get_active_medications": get_active_medications,
    "get_allergies": get_allergies,
    "get_recent_encounters": get_recent_encounters,
    "get_recent_labs": get_recent_labs,
}


def execute_tool(tool_name, tool_input, token, base_url):
    """Execute a tool by name."""
    func = TOOL_FUNCTIONS.get(tool_name)
    if not func:
        return {"success": False, "error": f"Unknown tool: {tool_name}", "citations": []}

    try:
        patient_id = tool_input.get("patient_id", "")
        return func(patient_id, token, base_url)
    except Exception as e:
        return {"success": False, "error": str(e), "citations": []}
