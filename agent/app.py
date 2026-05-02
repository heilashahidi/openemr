"""
Clinical Co-Pilot Agent Service
FastAPI app that uses Claude to answer PCP questions about patients via OpenEMR FHIR API.
"""

import os
import json
import time
import requests
import urllib3
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from anthropic import Anthropic
from langsmith.wrappers import wrap_anthropic
from langsmith.wrappers import wrap_anthropic
from langsmith.wrappers import wrap_anthropic
from tools import TOOLS, execute_tool
from verification import verify_response

urllib3.disable_warnings()

app = FastAPI(title="Clinical Co-Pilot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Config
OPENEMR_BASE = os.getenv("OPENEMR_BASE", "https://localhost:9300")
OPENEMR_CLIENT_ID = os.getenv("OPENEMR_CLIENT_ID", "")
OPENEMR_CLIENT_SECRET = os.getenv("OPENEMR_CLIENT_SECRET", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

client = wrap_anthropic(Anthropic(api_key=ANTHROPIC_API_KEY))

# Token cache
_token_cache = {"token": None, "expires_at": 0}


def get_openemr_token():
    """Get or refresh OAuth2 token for OpenEMR."""
    if _token_cache["token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    resp = requests.post(
        f"{OPENEMR_BASE}/oauth2/default/token",
        data={
            "grant_type": "password",
            "username": "admin",
            "password": "pass",
            "user_role": "users",
            "scope": "openid api:fhir user/Patient.read user/Condition.read user/MedicationRequest.read user/AllergyIntolerance.read user/Encounter.read user/Observation.read",
            "client_id": OPENEMR_CLIENT_ID,
            "client_secret": OPENEMR_CLIENT_SECRET,
        },
        verify=False,
    )
    if resp.status_code != 200:
        raise Exception(f"Token failed: {resp.status_code} {resp.text}")

    data = resp.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = time.time() + data.get("expires_in", 3600)
    return _token_cache["token"]


SYSTEM_PROMPT = """You are a Clinical Co-Pilot for a primary care physician (PCP).
You help the PCP by answering questions about their patients using data from OpenEMR.

RULES:
1. Every factual claim MUST cite a source. Use the FHIR resource IDs returned by tools.
2. If the record is silent on a topic, say "No [topic] documented in the record." Do NOT guess.
3. The patient-stated reason for visit is a signal, not confirmed truth. Say "The patient indicated they are here for X."
4. Always surface chronic conditions from the active problem list, even if not related to today's visit.
5. Keep pre-room briefings under 150 words so the PCP can read in 30 seconds.
6. For factual lookups, give a direct answer with citation. Don't ramble.
7. If a tool fails, say what failed and suggest the PCP check the chart directly.
8. Never make up medication names, lab values, or diagnoses not in the data.

TOOL SELECTION:
- For structured data (current medications, active conditions, allergies, lab values, vitals): use the specific structured tools (get_active_medications, get_active_conditions, get_allergies, get_recent_labs).
- For unstructured/historical questions (has the patient ever mentioned a symptom, any history of a complaint, what was discussed at prior visits, symptom patterns over time): use search_notes.
- For briefings: call structured tools first, then search_notes if the visit reason suggests a topic worth searching notes for.

When the PCP asks for a briefing, call tools in this order:
1. get_active_conditions - to know chronic conditions
2. get_active_medications - current med list
3. get_allergies - allergy list
4. get_recent_encounters - visit history and today's reason
5. get_recent_labs - if relevant to conditions

Structure briefings as:
- TODAY: What the visit appears to be about
- CHANGES: What's changed since last visit
- ACTIVE CONDITIONS: Chronic problems to keep in mind
"""


class ChatRequest(BaseModel):
    patient_id: str
    message: str
    conversation_history: list = []


class ChatResponse(BaseModel):
    response: str
    citations: list
    tools_called: list
    tokens_used: dict
    verified: bool


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Main chat endpoint. PCP sends a question about a patient."""
    token = get_openemr_token()
    tools_called = []
    citations = []
    total_input_tokens = 0
    total_output_tokens = 0

    # Build messages
    messages = []
    for msg in req.conversation_history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": f"[Patient ID: {req.patient_id}]\n\n{req.message}"})


    # Tool definitions for Claude
    tool_defs = [
        {
            "name": t["name"],
            "description": t["description"],
            "input_schema": t["input_schema"],
        }
        for t in TOOLS
    ]

    # Agent loop - let Claude call tools until it produces a final response
    max_iterations = 10
    for i in range(max_iterations):
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=messages,
            tools=tool_defs,
        )

        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens

        # Check if Claude wants to use tools
        if response.stop_reason == "tool_use":
            # Process tool calls
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input
                    tool_input["patient_id"] = req.patient_id

                    # Execute the tool
                    start = time.time()
                    result = execute_tool(tool_name, tool_input, token, OPENEMR_BASE)
                    elapsed = time.time() - start

                    tools_called.append({
                        "tool": tool_name,
                        "input": tool_input,
                        "latency_ms": round(elapsed * 1000),
                        "success": result.get("success", False),
                    })

                    # Collect citations from tool results
                    if result.get("citations"):
                        citations.extend(result["citations"])

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result.get("data", result.get("error", "Unknown error"))),
                    })

            # Add assistant message and tool results to conversation
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        else:
            # Claude produced a final text response
            final_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    final_text += block.text

            # Run verification
            verified, final_text = verify_response(final_text, citations)

            return ChatResponse(
                response=final_text,
                citations=citations,
                tools_called=tools_called,
                tokens_used={
                    "input": total_input_tokens,
                    "output": total_output_tokens,
                    "total": total_input_tokens + total_output_tokens,
                },
                verified=verified,
            )

    raise HTTPException(status_code=500, detail="Agent exceeded max iterations")


@app.get("/ui")
async def ui():
    return FileResponse("chat.html")

@app.get("/health")
async def health():
    return {"status": "ok"}
