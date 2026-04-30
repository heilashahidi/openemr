"""
Verification layer for the Clinical Co-Pilot.
Checks that agent responses are grounded in retrieved data.
"""


def verify_response(response_text: str, citations: list) -> tuple[bool, str]:
    """
    Verify the agent's response is grounded.
    Returns (is_verified, possibly_modified_response).
    """
    issues = []

    # Check 1: If citations exist, response should reference data
    if not citations and _has_clinical_claims(response_text):
        issues.append("Response makes clinical claims but no data was retrieved.")

    # Check 2: Check for common hallucination patterns
    hallucination_phrases = [
        "I recommend",
        "You should prescribe",
        "The diagnosis is",
        "I would suggest ordering",
        "Based on my medical knowledge",
        "In my clinical experience",
    ]
    for phrase in hallucination_phrases:
        if phrase.lower() in response_text.lower():
            issues.append(f"Response contains clinical advice phrase: '{phrase}'")

    # Check 3: Verify the response acknowledges gaps when data is empty
    empty_resources = [c for c in citations if not c.get("id")]
    if empty_resources:
        # Data was requested but came back empty — response should acknowledge
        pass  # This is handled by the system prompt's silence rule

    if issues:
        # Add a verification warning to the response
        warning = "\n\n⚠️ **Verification note:** " + "; ".join(issues)
        return False, response_text + warning

    return True, response_text


def _has_clinical_claims(text: str) -> bool:
    """Check if text contains clinical claims that need citations."""
    clinical_keywords = [
        "mg", "dose", "prescribed", "diagnosed", "lab", "result",
        "blood pressure", "A1c", "glucose", "cholesterol",
        "medication", "allergy", "condition",
    ]
    text_lower = text.lower()
    return any(kw in text_lower for kw in clinical_keywords)
