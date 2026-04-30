"""
Quick test script for the Clinical Co-Pilot agent.
Run the agent first: uvicorn app:app --port 8000
Then run this: python test_agent.py
"""

import requests
import json

AGENT_URL = "http://localhost:8000"

# Get the patient UUID from your OpenEMR instance
# Replace this with a real patient UUID from your FHIR API
PATIENT_ID = "REPLACE_WITH_PATIENT_UUID"

def test_briefing():
    print("=" * 50)
    print("TEST: Pre-room briefing (UC1)")
    print("=" * 50)
    resp = requests.post(f"{AGENT_URL}/chat", json={
        "patient_id": PATIENT_ID,
        "message": "Give me a pre-room briefing for this patient.",
    })
    data = resp.json()
    print(f"Response:\n{data['response']}\n")
    print(f"Tools called: {[t['tool'] for t in data['tools_called']]}")
    print(f"Citations: {len(data['citations'])}")
    print(f"Tokens: {data['tokens_used']}")
    print(f"Verified: {data['verified']}")
    print()

def test_factual_lookup():
    print("=" * 50)
    print("TEST: Factual lookup (UC2)")
    print("=" * 50)
    resp = requests.post(f"{AGENT_URL}/chat", json={
        "patient_id": PATIENT_ID,
        "message": "What medications is this patient currently on?",
    })
    data = resp.json()
    print(f"Response:\n{data['response']}\n")
    print(f"Tools called: {[t['tool'] for t in data['tools_called']]}")
    print(f"Verified: {data['verified']}")
    print()

def test_silence():
    print("=" * 50)
    print("TEST: Silence handling")
    print("=" * 50)
    resp = requests.post(f"{AGENT_URL}/chat", json={
        "patient_id": PATIENT_ID,
        "message": "Has this patient ever had a colonoscopy?",
    })
    data = resp.json()
    print(f"Response:\n{data['response']}\n")
    print(f"Verified: {data['verified']}")
    print()

if __name__ == "__main__":
    print("Clinical Co-Pilot Agent Test\n")
    
    # Check agent is running
    try:
        health = requests.get(f"{AGENT_URL}/health")
        print(f"Agent health: {health.json()}\n")
    except:
        print("ERROR: Agent not running. Start it with: uvicorn app:app --port 8000")
        exit(1)
    
    test_briefing()
    test_factual_lookup()
    test_silence()
