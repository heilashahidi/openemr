#!/usr/bin/env python3
"""
Seed realistic demo patients into OpenEMR via FHIR + Standard REST APIs.
Usage: python seed_data.py
"""

import requests
import json
import urllib3

urllib3.disable_warnings()

BASE = "https://openemr-production-8cd1.up.railway.app"
SITE = "default"
FHIR_URL = f"{BASE}/apis/{SITE}/fhir"
API_URL = f"{BASE}/apis/{SITE}/api"

# --- Step 1: Get OAuth2 token ---

def get_token():
    """Register a client and get a bearer token."""
    # Register client
    reg = requests.post(
        f"{BASE}/oauth2/{SITE}/registration",
        json={
            "application_type": "private",
            "redirect_uris": ["https://localhost"],
            "client_name": "SeedScript",
            "token_endpoint_auth_method": "client_secret_post",
            "contacts": ["admin@example.com"],
            "scope": "openid api:oemr api:fhir user/Patient.read user/Patient.write user/Encounter.read user/Condition.read user/MedicationRequest.read user/AllergyIntolerance.read user/Observation.read"
        },
        verify=False
    )
    if reg.status_code != 200:
        print(f"Registration failed: {reg.status_code} {reg.text}")
        return None
    
    client = reg.json()
    client_id = client["client_id"]
    client_secret = client["client_secret"]
    print(f"Client registered: {client_id}")
    print(f"⚠️  Enable the client in DB: UPDATE oauth_clients SET is_enabled=1 WHERE client_id='{client_id}';")
    input("Press Enter after enabling the client in the database...")

    # Get token
    token_resp = requests.post(
        f"{BASE}/oauth2/{SITE}/token",
        data={
            "grant_type": "password",
            "client_id": client_id,
            "client_secret": client_secret,
            "username": "admin",
            "password": "pass",
            "scope": "openid api:oemr api:fhir user/Patient.read user/Patient.write user/Encounter.read user/Condition.read user/MedicationRequest.read user/AllergyIntolerance.read user/Observation.read"
        },
        verify=False
    )
    if token_resp.status_code != 200:
        print(f"Token failed: {token_resp.status_code} {token_resp.text}")
        return None
    
    token = token_resp.json()["access_token"]
    print(f"Token acquired ✓")
    return token, client_id


def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# --- Step 2: Create patients via Standard REST API ---

def create_patient(token, patient_data):
    """Create a patient via Standard REST API."""
    resp = requests.post(
        f"{API_URL}/patient",
        json=patient_data,
        headers=headers(token),
        verify=False
    )
    if resp.status_code in [200, 201]:
        pid = resp.json().get("pid") or resp.json().get("id")
        uuid = resp.json().get("uuid", "")
        print(f"  Patient created: {patient_data['fname']} {patient_data['lname']} (pid={pid})")
        return resp.json()
    else:
        print(f"  Patient failed: {resp.status_code} {resp.text[:200]}")
        return None


# --- Step 3: Add clinical data via Standard REST API ---

def add_encounter(token, puuid, data):
    resp = requests.post(
        f"{API_URL}/patient/{puuid}/encounter",
        json=data,
        headers=headers(token),
        verify=False
    )
    if resp.status_code in [200, 201]:
        euuid = resp.json().get("uuid", "")
        print(f"    Encounter added: {data.get('reason', 'no reason')}")
        return resp.json()
    else:
        print(f"    Encounter failed: {resp.status_code} {resp.text[:200]}")
        return None


def add_condition(token, puuid, data):
    resp = requests.post(
        f"{API_URL}/patient/{puuid}/medical_problem",
        json=data,
        headers=headers(token),
        verify=False
    )
    if resp.status_code in [200, 201]:
        print(f"    Condition added: {data.get('title', '')}")
        return resp.json()
    else:
        print(f"    Condition failed: {resp.status_code} {resp.text[:200]}")
        return None


def add_medication(token, puuid, data):
    resp = requests.post(
        f"{API_URL}/patient/{puuid}/medication",
        json=data,
        headers=headers(token),
        verify=False
    )
    if resp.status_code in [200, 201]:
        print(f"    Medication added: {data.get('title', '')}")
        return resp.json()
    else:
        print(f"    Medication failed: {resp.status_code} {resp.text[:200]}")
        return None


def add_allergy(token, puuid, data):
    resp = requests.post(
        f"{API_URL}/patient/{puuid}/allergy",
        json=data,
        headers=headers(token),
        verify=False
    )
    if resp.status_code in [200, 201]:
        print(f"    Allergy added: {data.get('title', '')}")
        return resp.json()
    else:
        print(f"    Allergy failed: {resp.status_code} {resp.text[:200]}")
        return None


def add_vital(token, puuid, eid, data):
    resp = requests.post(
        f"{API_URL}/patient/{puuid}/encounter/{eid}/vital",
        json=data,
        headers=headers(token),
        verify=False
    )
    if resp.status_code in [200, 201]:
        print(f"    Vitals added: BP {data.get('bps','')}/{data.get('bpd','')}")
        return resp.json()
    else:
        print(f"    Vital failed: {resp.status_code} {resp.text[:200]}")
        return None


# --- Patient definitions ---

PATIENTS = [
    {
        "info": {
            "fname": "Maria",
            "lname": "Garcia",
            "DOB": "1968-03-15",
            "sex": "Female",
            "race": "hispanic",
            "street": "456 Oak Ave",
            "city": "Austin",
            "state": "Texas",
            "postal_code": "78701",
            "phone_home": "512-555-0142",
            "email": "maria.garcia@example.com"
        },
        "conditions": [
            {"title": "Type 2 diabetes mellitus", "diagnosis": "E11.9", "begdate": "2019-06-10"},
            {"title": "Essential hypertension", "diagnosis": "I10", "begdate": "2018-01-22"},
            {"title": "Hyperlipidemia", "diagnosis": "E78.5", "begdate": "2020-03-14"},
            {"title": "Obesity", "diagnosis": "E66.01", "begdate": "2017-09-05"},
        ],
        "medications": [
            {"title": "Metformin 1000mg", "dosage": "1000mg twice daily", "begdate": "2019-06-10"},
            {"title": "Lisinopril 20mg", "dosage": "20mg once daily", "begdate": "2018-02-01"},
            {"title": "Atorvastatin 40mg", "dosage": "40mg at bedtime", "begdate": "2020-03-20"},
        ],
        "allergies": [
            {"title": "Penicillin", "begdate": "2010-01-01"},
            {"title": "Sulfa drugs", "begdate": "2015-06-15"},
        ],
        "encounters": [
            {
                "reason": "Diabetes follow-up, feeling more tired than usual",
                "date": "2026-04-15",
                "vitals": {"bps": "142", "bpd": "88", "weight": "198", "height": "64", "pulse": "78", "temperature": "98.6"}
            },
            {
                "reason": "Medication review, blood pressure check",
                "date": "2026-01-20",
                "vitals": {"bps": "138", "bpd": "85", "weight": "195", "height": "64", "pulse": "74", "temperature": "98.4"}
            },
            {
                "reason": "Annual physical exam",
                "date": "2025-09-10",
                "vitals": {"bps": "145", "bpd": "92", "weight": "200", "height": "64", "pulse": "80", "temperature": "98.6"}
            },
        ],
        "description": "Rich chart — diabetic with multiple chronic conditions. Ideal for UC1 pre-room briefing demo."
    },
    {
        "info": {
            "fname": "James",
            "lname": "Thompson",
            "DOB": "1955-11-28",
            "sex": "Male",
            "street": "789 Pine St",
            "city": "Austin",
            "state": "Texas",
            "postal_code": "78704",
            "phone_home": "512-555-0198",
            "email": "james.t@example.com"
        },
        "conditions": [
            {"title": "Coronary artery disease", "diagnosis": "I25.10", "begdate": "2015-04-20"},
            {"title": "Type 2 diabetes mellitus", "diagnosis": "E11.9", "begdate": "2012-08-15"},
            {"title": "Chronic kidney disease stage 3", "diagnosis": "N18.3", "begdate": "2021-02-10"},
            {"title": "Essential hypertension", "diagnosis": "I10", "begdate": "2010-05-01"},
            {"title": "Atrial fibrillation", "diagnosis": "I48.91", "begdate": "2022-11-03"},
        ],
        "medications": [
            {"title": "Metformin 500mg", "dosage": "500mg twice daily", "begdate": "2012-08-15"},
            {"title": "Aspirin 81mg", "dosage": "81mg once daily", "begdate": "2015-04-25"},
            {"title": "Metoprolol 50mg", "dosage": "50mg twice daily", "begdate": "2015-05-01"},
            {"title": "Apixaban 5mg", "dosage": "5mg twice daily", "begdate": "2022-11-10"},
            {"title": "Losartan 100mg", "dosage": "100mg once daily", "begdate": "2010-05-15"},
            {"title": "Empagliflozin 10mg", "dosage": "10mg once daily", "begdate": "2023-03-01"},
        ],
        "allergies": [
            {"title": "ACE inhibitors (cough)", "begdate": "2010-04-01"},
        ],
        "encounters": [
            {
                "reason": "Right knee pain for 2 weeks",
                "date": "2026-04-22",
                "vitals": {"bps": "136", "bpd": "82", "weight": "210", "height": "70", "pulse": "68", "temperature": "98.4"}
            },
            {
                "reason": "Cardiology follow-up, medication adjustment",
                "date": "2026-02-14",
                "vitals": {"bps": "130", "bpd": "78", "weight": "212", "height": "70", "pulse": "72", "temperature": "98.6"}
            },
        ],
        "description": "Complex patient — cardiac + renal + diabetes. Today's visit is knee pain, but chronic conditions must still surface. Tests UC1 visit-reason-as-lens and UC3 pivot."
    },
    {
        "info": {
            "fname": "Emily",
            "lname": "Chen",
            "DOB": "1992-07-04",
            "sex": "Female",
            "street": "123 Elm Dr",
            "city": "Austin",
            "state": "Texas",
            "postal_code": "78745",
            "phone_home": "512-555-0267",
            "email": "emily.chen@example.com"
        },
        "conditions": [],
        "medications": [],
        "allergies": [],
        "encounters": [
            {
                "reason": "New patient visit, headaches for 3 months",
                "date": "2026-04-28",
                "vitals": {"bps": "118", "bpd": "72", "weight": "135", "height": "65", "pulse": "68", "temperature": "98.6"}
            },
        ],
        "description": "Sparse chart — new patient, no prior history. Tests 'silence is silence' verification path."
    },
    {
        "info": {
            "fname": "Robert",
            "lname": "Williams",
            "DOB": "1975-02-19",
            "sex": "Male",
            "street": "321 Cedar Ln",
            "city": "Austin",
            "state": "Texas",
            "postal_code": "78702",
            "phone_home": "512-555-0334",
            "email": "rob.williams@example.com"
        },
        "conditions": [
            {"title": "Major depressive disorder, recurrent", "diagnosis": "F33.1", "begdate": "2020-01-15"},
            {"title": "Generalized anxiety disorder", "diagnosis": "F41.1", "begdate": "2020-01-15"},
            {"title": "Essential hypertension", "diagnosis": "I10", "begdate": "2022-06-01"},
        ],
        "medications": [
            {"title": "Sertraline 100mg", "dosage": "100mg once daily", "begdate": "2020-02-01"},
            {"title": "Amlodipine 5mg", "dosage": "5mg once daily", "begdate": "2022-06-15"},
        ],
        "allergies": [
            {"title": "Latex", "begdate": "2005-03-01"},
        ],
        "encounters": [
            {
                "reason": "Depression follow-up, sleep has been worse",
                "date": "2026-04-25",
                "vitals": {"bps": "128", "bpd": "80", "weight": "185", "height": "71", "pulse": "76", "temperature": "98.4"}
            },
            {
                "reason": "Anxiety management, medication check",
                "date": "2026-02-10",
                "vitals": {"bps": "132", "bpd": "84", "weight": "183", "height": "71", "pulse": "80", "temperature": "98.6"}
            },
            {
                "reason": "Annual wellness visit",
                "date": "2025-08-20",
                "vitals": {"bps": "130", "bpd": "82", "weight": "180", "height": "71", "pulse": "72", "temperature": "98.6"}
            },
        ],
        "description": "Mental health + hypertension. Tests UC1 with behavioral health context and UC4 post-visit recap."
    },
]


# --- Main ---

def main():
    print("=" * 50)
    print("OpenEMR Seed Script")
    print(f"Target: {BASE}")
    print("=" * 50)
    
    result = get_token()
    if not result:
        print("Failed to get token. Exiting.")
        return
    
    token, client_id = result
    
    for i, patient in enumerate(PATIENTS):
        print(f"\n--- Patient {i+1}: {patient['info']['fname']} {patient['info']['lname']} ---")
        print(f"    Purpose: {patient['description']}")
        
        # Create patient
        p = create_patient(token, patient["info"])
        if not p:
            continue
        
        puuid = p.get("uuid", "")
        if not puuid:
            print("    No UUID returned, skipping clinical data")
            continue
        
        # Add conditions
        for cond in patient["conditions"]:
            add_condition(token, puuid, cond)
        
        # Add medications
        for med in patient["medications"]:
            add_medication(token, puuid, med)
        
        # Add allergies
        for allergy in patient["allergies"]:
            add_allergy(token, puuid, allergy)
        
        # Add encounters with vitals
        for enc in patient["encounters"]:
            enc_data = {"reason": enc["reason"], "date": enc["date"]}
            e = add_encounter(token, puuid, enc_data)
            if e and enc.get("vitals"):
                euuid = e.get("uuid", "")
                if euuid:
                    add_vital(token, puuid, euuid, enc["vitals"])
    
    print("\n" + "=" * 50)
    print("Seeding complete!")
    print(f"Don't forget to disable the OAuth client when done:")
    print(f"  UPDATE oauth_clients SET is_enabled=0 WHERE client_id='{client_id}';")
    print("=" * 50)


if __name__ == "__main__":
    main()
