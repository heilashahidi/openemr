"""
Strict Pydantic schemas for document extraction.
Week 2 requirement: lab_pdf and intake_form with source citations.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import date


# ── Source Citation ──
class SourceCitation(BaseModel):
    """Machine-readable citation metadata per Week 2 spec."""
    source_type: str = Field(description="Type of source: 'lab_pdf' or 'intake_form'")
    source_id: str = Field(description="Document ID or filename")
    page_or_section: Optional[str] = Field(default=None, description="Page number or section name")
    field_or_chunk_id: Optional[str] = Field(default=None, description="Specific field or chunk identifier")
    quote_or_value: Optional[str] = Field(default=None, description="Exact value extracted from the source")


# ── Lab PDF Schema ──
class LabResult(BaseModel):
    """A single lab test result extracted from a lab PDF."""
    test_name: str = Field(description="Name of the lab test (e.g., 'Glucose', 'HbA1c')")
    value: str = Field(description="The numeric or text result value")
    unit: str = Field(description="Unit of measurement (e.g., 'mg/dL', '%')")
    reference_range: str = Field(description="Normal reference range (e.g., '70-100')")
    collection_date: Optional[str] = Field(default=None, description="Date the specimen was collected (YYYY-MM-DD)")
    abnormal_flag: Optional[str] = Field(default=None, description="Abnormal flag: 'H' (high), 'L' (low), 'C' (critical), or None")
    source_citation: SourceCitation = Field(description="Citation pointing back to the source document")


class LabPDFExtraction(BaseModel):
    """Complete extraction from a lab report PDF."""
    patient_name: str = Field(description="Patient full name from the lab report")
    patient_dob: Optional[str] = Field(default=None, description="Patient date of birth")
    patient_mrn: Optional[str] = Field(default=None, description="Medical record number")
    ordering_provider: Optional[str] = Field(default=None, description="Provider who ordered the labs")
    collection_date: str = Field(description="Date specimens were collected (YYYY-MM-DD)")
    report_date: Optional[str] = Field(default=None, description="Date the report was finalized")
    report_status: Optional[str] = Field(default=None, description="Report status: 'Final', 'Preliminary', etc.")
    specimen_type: Optional[str] = Field(default=None, description="Specimen type / source (e.g., 'Whole blood EDTA', 'Serum', 'Plasma', 'Urine'). Capture the specimen description verbatim if shown.")
    specimen_volume: Optional[str] = Field(default=None, description="Specimen volume with unit (e.g., '5 mL', '10 cc')")
    specimen_notes: Optional[str] = Field(default=None, description="Any notes about the specimen — collection method, conditions, fasting status, hemolysis, etc.")
    lab_results: list[LabResult] = Field(description="List of individual lab test results")
    interpretive_comments: Optional[str] = Field(default=None, description="Free-text interpretive comments / notes from the lab report (e.g., 'Mild anemia, recommend iron studies'). Capture all narrative comment sections verbatim.")
    source_document: str = Field(description="Original filename or document ID")
    extraction_confidence: Optional[float] = Field(default=None, description="Overall extraction confidence 0.0-1.0")


# ── Intake Form Schema ──
class IntakeMedication(BaseModel):
    """A medication listed on the intake form."""
    medication_name: str = Field(description="Name of the medication")
    dose: Optional[str] = Field(default=None, description="Dose (e.g., '200mg')")
    frequency: Optional[str] = Field(default=None, description="How often taken (e.g., 'twice daily')")
    purpose: Optional[str] = Field(default=None, description="Reason for taking")
    source_citation: SourceCitation = Field(description="Citation to source")


class IntakeAllergy(BaseModel):
    """An allergy listed on the intake form."""
    allergen: str = Field(description="Substance the patient is allergic to")
    reaction: Optional[str] = Field(default=None, description="Type of reaction")
    source_citation: SourceCitation = Field(description="Citation to source")


class FamilyHistoryEntry(BaseModel):
    """A single family history entry."""
    relation: str = Field(description="Family member relationship (e.g., 'Mother', 'Father')")
    conditions: list[str] = Field(description="Medical conditions")
    status: Optional[str] = Field(default=None, description="Alive/deceased, age")
    source_citation: SourceCitation = Field(description="Citation to source")


class IntakeFormExtraction(BaseModel):
    """Complete extraction from a patient intake form."""
    # Demographics
    patient_name: str = Field(description="Patient full name")
    patient_dob: Optional[str] = Field(default=None, description="Date of birth")
    patient_age: Optional[int] = Field(default=None, description="Age in years")
    patient_sex: Optional[str] = Field(default=None, description="Sex (Male/Female)")
    patient_phone: Optional[str] = Field(default=None, description="Phone number")
    patient_address: Optional[str] = Field(default=None, description="Full address")
    emergency_contact: Optional[str] = Field(default=None, description="Emergency contact name and phone")
    insurance: Optional[str] = Field(default=None, description="Insurance provider and policy")
    
    # Clinical
    chief_concern: str = Field(description="Primary reason for visit in patient's own words")
    current_medications: list[IntakeMedication] = Field(description="List of current medications")
    allergies: list[IntakeAllergy] = Field(description="List of known allergies")
    family_history: list[FamilyHistoryEntry] = Field(default_factory=list, description="Family medical history")
    social_history: Optional[str] = Field(default=None, description="Social history summary")
    past_medical_history: list[str] = Field(default_factory=list, description="Past medical history / problem list (each entry is one condition, e.g. 'Hypertension', 'Type 2 diabetes')")
    surgical_history: list[str] = Field(default_factory=list, description="Past surgical history (each entry is one surgery, e.g. 'Appendectomy 2010', 'Cholecystectomy 2018')")
    treating_physicians: Optional[str] = Field(default=None, description="Treating physicians / care team — names and roles (e.g. 'Dr. Smith (PCP), Dr. Jones (Cardiologist)')")
    review_of_systems: Optional[dict] = Field(default=None, description="Review of systems by body system")
    
    # Metadata
    form_date: Optional[str] = Field(default=None, description="Date the form was completed")
    source_document: str = Field(description="Original filename or document ID")
    extraction_confidence: Optional[float] = Field(default=None, description="Overall extraction confidence 0.0-1.0")


# ── Validation helpers ──
def validate_lab_extraction(extraction: LabPDFExtraction) -> dict:
    """Validate a lab extraction against schema requirements."""
    issues = []
    
    if not extraction.lab_results:
        issues.append("No lab results extracted")
    
    for i, result in enumerate(extraction.lab_results):
        if not result.test_name:
            issues.append(f"Result {i}: missing test_name")
        if not result.value:
            issues.append(f"Result {i} ({result.test_name}): missing value")
        if not result.unit:
            issues.append(f"Result {i} ({result.test_name}): missing unit")
        if not result.reference_range:
            issues.append(f"Result {i} ({result.test_name}): missing reference_range")
        if not result.source_citation:
            issues.append(f"Result {i} ({result.test_name}): missing source_citation")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "result_count": len(extraction.lab_results),
        "abnormal_count": len([r for r in extraction.lab_results if r.abnormal_flag]),
    }


def validate_intake_extraction(extraction: IntakeFormExtraction) -> dict:
    """Validate an intake form extraction against schema requirements."""
    issues = []
    
    if not extraction.patient_name:
        issues.append("Missing patient_name")
    if not extraction.chief_concern:
        issues.append("Missing chief_concern")
    if not extraction.current_medications:
        issues.append("No medications extracted")
    if not extraction.allergies:
        issues.append("No allergies extracted")
    
    for i, med in enumerate(extraction.current_medications):
        if not med.medication_name:
            issues.append(f"Medication {i}: missing medication_name")
        if not med.source_citation:
            issues.append(f"Medication {i} ({med.medication_name}): missing source_citation")
    
    for i, allergy in enumerate(extraction.allergies):
        if not allergy.allergen:
            issues.append(f"Allergy {i}: missing allergen")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "medication_count": len(extraction.current_medications),
        "allergy_count": len(extraction.allergies),
        "family_history_count": len(extraction.family_history),
    }
