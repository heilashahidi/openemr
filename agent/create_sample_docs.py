"""
Generate sample clinical documents for Week 2 testing.
Creates: sample_lab_report.pdf, sample_intake_form.pdf
Run: python3 create_sample_docs.py
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import os

OUTPUT_DIR = "sample_docs"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def create_lab_pdf():
    """Create a realistic lab report PDF."""
    filepath = os.path.join(OUTPUT_DIR, "sample_lab_report.pdf")
    doc = SimpleDocTemplate(filepath, pagesize=letter, topMargin=0.5*inch)
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=16, spaceAfter=6)
    header_style = ParagraphStyle('Header', parent=styles['Normal'], fontSize=10, textColor=colors.grey)
    section_style = ParagraphStyle('Section', parent=styles['Heading2'], fontSize=12, spaceBefore=12)
    
    elements = []
    
    # Header
    elements.append(Paragraph("Austin Regional Medical Center", title_style))
    elements.append(Paragraph("Laboratory Report", styles['Heading2']))
    elements.append(Spacer(1, 6))
    
    # Patient info
    patient_info = [
        ["Patient:", "David Nakamura", "DOB:", "06/22/1958"],
        ["MRN:", "100008", "Collection Date:", "04/25/2026"],
        ["Ordering Provider:", "Dr. Martinez", "Report Date:", "04/26/2026"],
        ["Account:", "ACC-2026-04821", "Status:", "Final"],
    ]
    
    t = Table(patient_info, colWidths=[1.2*inch, 2*inch, 1.2*inch, 2*inch])
    t.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 12))
    
    # Comprehensive Metabolic Panel
    elements.append(Paragraph("Comprehensive Metabolic Panel", section_style))
    cmp_data = [
        ["Test", "Result", "Unit", "Reference Range", "Flag"],
        ["Glucose", "187", "mg/dL", "70-100", "H"],
        ["BUN", "32", "mg/dL", "7-20", "H"],
        ["Creatinine", "1.8", "mg/dL", "0.7-1.3", "H"],
        ["eGFR", "38", "mL/min/1.73m²", ">60", "L"],
        ["Sodium", "139", "mmol/L", "136-145", ""],
        ["Potassium", "4.8", "mmol/L", "3.5-5.0", ""],
        ["Chloride", "101", "mmol/L", "98-106", ""],
        ["CO2", "22", "mmol/L", "23-29", "L"],
        ["Calcium", "9.1", "mg/dL", "8.5-10.5", ""],
        ["Total Protein", "6.8", "g/dL", "6.0-8.3", ""],
        ["Albumin", "3.4", "g/dL", "3.5-5.5", "L"],
        ["Bilirubin Total", "0.8", "mg/dL", "0.1-1.2", ""],
        ["Alk Phosphatase", "92", "U/L", "44-147", ""],
        ["AST (SGOT)", "28", "U/L", "10-40", ""],
        ["ALT (SGPT)", "31", "U/L", "7-56", ""],
    ]
    
    t = Table(cmp_data, colWidths=[1.8*inch, 0.8*inch, 1.2*inch, 1.2*inch, 0.6*inch])
    t.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.2, 0.2, 0.3)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.Color(0.95, 0.95, 0.95)]),
        ('TEXTCOLOR', (4, 1), (4, -1), colors.red),
        ('FONTNAME', (4, 1), (4, -1), 'Helvetica-Bold'),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 12))
    
    # HbA1c
    elements.append(Paragraph("Hemoglobin A1c", section_style))
    a1c_data = [
        ["Test", "Result", "Unit", "Reference Range", "Flag"],
        ["HbA1c", "8.2", "%", "<7.0", "H"],
        ["Est. Average Glucose", "189", "mg/dL", "", ""],
    ]
    t = Table(a1c_data, colWidths=[1.8*inch, 0.8*inch, 1.2*inch, 1.2*inch, 0.6*inch])
    t.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.2, 0.2, 0.3)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('TEXTCOLOR', (4, 1), (4, -1), colors.red),
        ('FONTNAME', (4, 1), (4, -1), 'Helvetica-Bold'),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 12))
    
    # Lipid Panel
    elements.append(Paragraph("Lipid Panel", section_style))
    lipid_data = [
        ["Test", "Result", "Unit", "Reference Range", "Flag"],
        ["Total Cholesterol", "218", "mg/dL", "<200", "H"],
        ["Triglycerides", "195", "mg/dL", "<150", "H"],
        ["HDL Cholesterol", "38", "mg/dL", ">40", "L"],
        ["LDL Cholesterol", "141", "mg/dL", "<100", "H"],
        ["VLDL Cholesterol", "39", "mg/dL", "5-40", ""],
    ]
    t = Table(lipid_data, colWidths=[1.8*inch, 0.8*inch, 1.2*inch, 1.2*inch, 0.6*inch])
    t.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.2, 0.2, 0.3)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('TEXTCOLOR', (4, 1), (4, -1), colors.red),
        ('FONTNAME', (4, 1), (4, -1), 'Helvetica-Bold'),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 12))
    
    # BNP
    elements.append(Paragraph("Cardiac Markers", section_style))
    cardiac_data = [
        ["Test", "Result", "Unit", "Reference Range", "Flag"],
        ["BNP", "485", "pg/mL", "<100", "H"],
    ]
    t = Table(cardiac_data, colWidths=[1.8*inch, 0.8*inch, 1.2*inch, 1.2*inch, 0.6*inch])
    t.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.2, 0.2, 0.3)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('TEXTCOLOR', (4, 1), (4, -1), colors.red),
        ('FONTNAME', (4, 1), (4, -1), 'Helvetica-Bold'),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 12))
    
    # CBC
    elements.append(Paragraph("Complete Blood Count", section_style))
    cbc_data = [
        ["Test", "Result", "Unit", "Reference Range", "Flag"],
        ["WBC", "7.2", "x10³/µL", "4.5-11.0", ""],
        ["RBC", "4.1", "x10⁶/µL", "4.5-5.5", "L"],
        ["Hemoglobin", "12.8", "g/dL", "13.5-17.5", "L"],
        ["Hematocrit", "38.2", "%", "41-53", "L"],
        ["MCV", "93", "fL", "80-100", ""],
        ["Platelets", "198", "x10³/µL", "150-400", ""],
    ]
    t = Table(cbc_data, colWidths=[1.8*inch, 0.8*inch, 1.2*inch, 1.2*inch, 0.6*inch])
    t.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.2, 0.2, 0.3)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('TEXTCOLOR', (4, 1), (4, -1), colors.red),
        ('FONTNAME', (4, 1), (4, -1), 'Helvetica-Bold'),
    ]))
    elements.append(t)
    
    doc.build(elements)
    print(f"✅ Lab report created: {filepath}")
    return filepath


def create_intake_form():
    """Create a realistic patient intake form PDF."""
    filepath = os.path.join(OUTPUT_DIR, "sample_intake_form.pdf")
    doc = SimpleDocTemplate(filepath, pagesize=letter, topMargin=0.5*inch)
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=16, spaceAfter=6)
    section_style = ParagraphStyle('Section', parent=styles['Heading2'], fontSize=12, spaceBefore=12, spaceAfter=6)
    field_style = ParagraphStyle('Field', parent=styles['Normal'], fontSize=10, spaceBefore=2, spaceAfter=2)
    
    elements = []
    
    # Header
    elements.append(Paragraph("Patient Intake Form", title_style))
    elements.append(Paragraph("Austin Family Medicine Clinic", styles['Heading3']))
    elements.append(Spacer(1, 12))
    
    # Demographics
    elements.append(Paragraph("Patient Information", section_style))
    demo_data = [
        ["Full Name:", "Angela Washington", "Date:", "04/27/2026"],
        ["Date of Birth:", "01/30/1984", "Age:", "42"],
        ["Sex:", "Female", "Phone:", "(512) 555-0589"],
        ["Address:", "215 Magnolia Blvd, Austin, TX 78723", "", ""],
        ["Emergency Contact:", "Marcus Washington (husband)", "Phone:", "(512) 555-0590"],
        ["Insurance:", "Blue Cross Blue Shield", "Policy #:", "BCB-9847261"],
    ]
    t = Table(demo_data, colWidths=[1.3*inch, 2.3*inch, 0.8*inch, 2*inch])
    t.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 12))
    
    # Chief Concern
    elements.append(Paragraph("Reason for Visit", section_style))
    elements.append(Paragraph(
        "Joint pain flare in both hands and wrists for the past 2 weeks. Getting worse. "
        "Also having increased fatigue and noticed a rash on my cheeks that comes and goes. "
        "My lupus medications don't seem to be helping as much as they used to.",
        field_style
    ))
    elements.append(Spacer(1, 12))
    
    # Current Medications
    elements.append(Paragraph("Current Medications", section_style))
    med_data = [
        ["Medication", "Dose", "Frequency", "Purpose"],
        ["Hydroxychloroquine", "200mg", "Twice daily", "Lupus"],
        ["Mycophenolate", "1000mg", "Twice daily", "Lupus nephritis"],
        ["Prednisone", "5mg", "Once daily", "Lupus/inflammation"],
        ["Duloxetine", "60mg", "Once daily", "Depression/pain"],
        ["Levothyroxine", "75mcg", "Once daily", "Thyroid"],
        ["Ferrous sulfate", "325mg", "Twice daily", "Anemia"],
        ["Vitamin D3", "2000 IU", "Once daily", "Supplement"],
        ["Calcium carbonate", "600mg", "Twice daily", "Bone health"],
    ]
    t = Table(med_data, colWidths=[1.5*inch, 0.8*inch, 1.2*inch, 1.5*inch])
    t.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.2, 0.2, 0.3)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.Color(0.95, 0.95, 0.95)]),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 12))
    
    # Allergies
    elements.append(Paragraph("Allergies", section_style))
    allergy_data = [
        ["Allergen", "Reaction"],
        ["NSAIDs (ibuprofen, naproxen)", "GI bleeding"],
        ["Trimethoprim", "Skin rash"],
    ]
    t = Table(allergy_data, colWidths=[2.5*inch, 2.5*inch])
    t.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.2, 0.2, 0.3)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 12))
    
    # Family History
    elements.append(Paragraph("Family History", section_style))
    elements.append(Paragraph(
        "Mother: Rheumatoid arthritis, hypertension. Died age 71 (stroke).<br/>"
        "Father: Type 2 diabetes, coronary artery disease. Alive, age 73.<br/>"
        "Sister: Systemic lupus erythematosus. Alive, age 45.<br/>"
        "No family history of cancer.",
        field_style
    ))
    elements.append(Spacer(1, 12))
    
    # Social History
    elements.append(Paragraph("Social History", section_style))
    elements.append(Paragraph(
        "Non-smoker. Occasional alcohol (1-2 drinks/month). No recreational drugs. "
        "Works as a school counselor. Married with two children (ages 8 and 12). "
        "Reports high stress at work contributing to fatigue. "
        "Exercises when able but limited by joint pain — usually walking 2-3 times per week.",
        field_style
    ))
    elements.append(Spacer(1, 12))
    
    # Review of Systems
    elements.append(Paragraph("Review of Systems", section_style))
    ros_data = [
        ["System", "Symptoms"],
        ["Constitutional", "Fatigue (worsening), no fever, no weight change"],
        ["HEENT", "No headache, no vision changes"],
        ["Cardiovascular", "No chest pain, no palpitations, no edema"],
        ["Respiratory", "No shortness of breath, no cough"],
        ["GI", "No nausea, no abdominal pain"],
        ["Musculoskeletal", "Joint pain bilateral hands/wrists, morning stiffness ~45 min"],
        ["Skin", "Malar rash on cheeks, comes and goes with sun exposure"],
        ["Neurological", "No numbness, no weakness"],
        ["Psychiatric", "Anxiety increased, sleep poor (5-6 hrs), mood low"],
    ]
    t = Table(ros_data, colWidths=[1.3*inch, 4.5*inch])
    t.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.2, 0.2, 0.3)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.Color(0.95, 0.95, 0.95)]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(t)
    
    # Signature
    elements.append(Spacer(1, 24))
    elements.append(Paragraph("Patient Signature: Angela Washington", field_style))
    elements.append(Paragraph("Date: 04/27/2026", field_style))
    
    doc.build(elements)
    print(f"✅ Intake form created: {filepath}")
    return filepath


if __name__ == "__main__":
    print("Creating sample clinical documents...\n")
    create_lab_pdf()
    create_intake_form()
    print(f"\nDocuments saved to {OUTPUT_DIR}/")
