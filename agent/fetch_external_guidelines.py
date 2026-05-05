"""
External Guideline Fetcher for Clinical Co-Pilot (Week 2).
Pulls clinical data from OpenFDA (drug labels) and PubMed (guideline abstracts).
Both APIs are free, no authentication required.

Run: python3 fetch_external_guidelines.py
"""

import json
import os
import time
import requests

GUIDELINES_DIR = os.path.join(os.path.dirname(__file__), "external_corpus")
os.makedirs(GUIDELINES_DIR, exist_ok=True)


# ═══════════════════════════════════════════
# OpenFDA — Drug Label Information
# ═══════════════════════════════════════════

OPENFDA_BASE = "https://api.fda.gov/drug/label.json"

# Medications from our patient population
MEDICATIONS = [
    "metformin",
    "atorvastatin",
    "lisinopril",
    "amlodipine",
    "carvedilol",
    "furosemide",
    "apixaban",
    "gabapentin",
    "losartan",
    "empagliflozin",
    "hydroxychloroquine",
    "mycophenolate",
    "prednisone",
    "duloxetine",
    "sertraline",
    "sumatriptan",
    "levothyroxine",
    "semaglutide",
    "topiramate",
    "aspirin",
]


def fetch_openfda_drug(drug_name: str) -> dict:
    """Fetch drug label from OpenFDA."""
    try:
        resp = requests.get(
            OPENFDA_BASE,
            params={"search": f"openfda.generic_name:{drug_name}", "limit": 1},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("results"):
                return data["results"][0]
    except Exception as e:
        print(f"  ⚠ OpenFDA error for {drug_name}: {e}")
    return {}


def extract_drug_info(label: dict, drug_name: str) -> str:
    """Extract key clinical information from an FDA drug label."""
    sections = []

    # Get the brand name
    brand = ""
    if label.get("openfda", {}).get("brand_name"):
        brand = label["openfda"]["brand_name"][0]

    sections.append(f"# FDA Drug Label: {drug_name.title()}" + (f" ({brand})" if brand else ""))
    sections.append("")
    sections.append("## Source")
    sections.append(f"U.S. Food and Drug Administration. Drug Label for {drug_name}. OpenFDA API. Public domain.")
    sections.append("")

    # Indications
    if label.get("indications_and_usage"):
        text = label["indications_and_usage"][0][:1000]
        sections.append("## Indications and Usage")
        sections.append(text)
        sections.append("")

    # Dosage
    if label.get("dosage_and_administration"):
        text = label["dosage_and_administration"][0][:1000]
        sections.append("## Dosage and Administration")
        sections.append(text)
        sections.append("")

    # Warnings
    if label.get("warnings_and_cautions") or label.get("warnings"):
        text = (label.get("warnings_and_cautions") or label.get("warnings", [""]))[0][:1000]
        sections.append("## Warnings and Precautions")
        sections.append(text)
        sections.append("")

    # Contraindications
    if label.get("contraindications"):
        text = label["contraindications"][0][:800]
        sections.append("## Contraindications")
        sections.append(text)
        sections.append("")

    # Drug interactions
    if label.get("drug_interactions"):
        text = label["drug_interactions"][0][:800]
        sections.append("## Drug Interactions")
        sections.append(text)
        sections.append("")

    # Adverse reactions
    if label.get("adverse_reactions"):
        text = label["adverse_reactions"][0][:800]
        sections.append("## Adverse Reactions")
        sections.append(text)
        sections.append("")

    # Use in specific populations
    if label.get("use_in_specific_populations"):
        text = label["use_in_specific_populations"][0][:600]
        sections.append("## Use in Specific Populations")
        sections.append(text)
        sections.append("")

    return "\n".join(sections)


def fetch_all_drug_labels():
    """Fetch and save drug labels for all patient medications."""
    print("\n💊 OPENFDA — Fetching Drug Labels...")
    fetched = 0

    for drug in MEDICATIONS:
        filepath = os.path.join(GUIDELINES_DIR, f"fda_drug_{drug}.md")

        # Skip if already fetched
        if os.path.exists(filepath):
            print(f"  ⏭ {drug}: already fetched")
            continue

        label = fetch_openfda_drug(drug)
        if label:
            content = extract_drug_info(label, drug)
            if len(content) > 200:  # Only save if we got meaningful content
                with open(filepath, "w") as f:
                    f.write(content)
                print(f"  ✅ {drug}: saved ({len(content)} chars)")
                fetched += 1
            else:
                print(f"  ⚠ {drug}: insufficient label data")
        else:
            print(f"  ❌ {drug}: not found in OpenFDA")

        time.sleep(0.5)  # Rate limit: be polite

    print(f"\n  Fetched {fetched} drug labels from OpenFDA")
    return fetched


# ═══════════════════════════════════════════
# PubMed — Clinical Guideline Abstracts
# ═══════════════════════════════════════════

PUBMED_SEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_FETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# Clinical guideline searches relevant to our patients
GUIDELINE_SEARCHES = [
    {"query": "type 2 diabetes management guidelines 2024", "filename": "pubmed_diabetes_guidelines.md", "title": "Type 2 Diabetes Management"},
    {"query": "heart failure reduced ejection fraction treatment guidelines 2024", "filename": "pubmed_heart_failure_guidelines.md", "title": "Heart Failure with Reduced EF"},
    {"query": "chronic kidney disease management primary care guidelines 2024", "filename": "pubmed_ckd_guidelines.md", "title": "Chronic Kidney Disease Management"},
    {"query": "systemic lupus erythematosus treatment guidelines 2024", "filename": "pubmed_lupus_guidelines.md", "title": "Systemic Lupus Erythematosus"},
    {"query": "COPD exacerbation management guidelines 2024", "filename": "pubmed_copd_guidelines.md", "title": "COPD Exacerbation Management"},
    {"query": "major depressive disorder treatment primary care 2024", "filename": "pubmed_depression_guidelines.md", "title": "Major Depressive Disorder Treatment"},
    {"query": "migraine prevention treatment guidelines 2024", "filename": "pubmed_migraine_guidelines.md", "title": "Migraine Prevention and Treatment"},
    {"query": "hypertension management primary care guidelines 2024", "filename": "pubmed_hypertension_guidelines.md", "title": "Hypertension Management"},
    {"query": "atrial fibrillation anticoagulation guidelines 2024", "filename": "pubmed_afib_guidelines.md", "title": "Atrial Fibrillation Anticoagulation"},
    {"query": "anemia evaluation primary care guidelines 2024", "filename": "pubmed_anemia_guidelines.md", "title": "Anemia Evaluation in Primary Care"},
]


def search_pubmed(query: str, max_results: int = 5) -> list[str]:
    """Search PubMed and return PMIDs."""
    try:
        resp = requests.get(
            PUBMED_SEARCH,
            params={
                "db": "pubmed",
                "term": query,
                "retmax": max_results,
                "retmode": "json",
                "sort": "relevance",
            },
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        print(f"  ⚠ PubMed search error: {e}")
    return []


def fetch_pubmed_abstracts(pmids: list[str]) -> str:
    """Fetch abstracts for a list of PMIDs."""
    if not pmids:
        return ""

    try:
        resp = requests.get(
            PUBMED_FETCH,
            params={
                "db": "pubmed",
                "id": ",".join(pmids),
                "rettype": "abstract",
                "retmode": "text",
            },
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.text
    except Exception as e:
        print(f"  ⚠ PubMed fetch error: {e}")
    return ""


def format_pubmed_guideline(title: str, query: str, abstracts: str) -> str:
    """Format PubMed abstracts into a guideline markdown file."""
    sections = [
        f"# PubMed Evidence: {title}",
        "",
        "## Source",
        f"National Library of Medicine / PubMed. Search: \"{query}\". Retrieved via NCBI E-utilities API. Public domain — U.S. Government work.",
        "",
        "## Key Evidence from Published Guidelines",
        "",
    ]

    # Split abstracts by article
    articles = abstracts.split("\n\n\n")
    for i, article in enumerate(articles[:5]):  # Limit to 5
        article = article.strip()
        if len(article) > 100:
            # Extract title if present (usually first line)
            lines = article.split("\n")
            if lines:
                sections.append(f"### Article {i+1}")
                sections.append(article[:2000])  # Cap at 2000 chars per article
                sections.append("")

    return "\n".join(sections)


def fetch_all_pubmed_guidelines():
    """Fetch and save PubMed guideline abstracts."""
    print("\n📚 PUBMED — Fetching Clinical Guideline Abstracts...")
    fetched = 0

    for search in GUIDELINE_SEARCHES:
        filepath = os.path.join(GUIDELINES_DIR, search["filename"])

        # Skip if already fetched
        if os.path.exists(filepath):
            print(f"  ⏭ {search['title']}: already fetched")
            continue

        # Search
        pmids = search_pubmed(search["query"])
        if not pmids:
            print(f"  ❌ {search['title']}: no results")
            continue

        # Fetch abstracts
        abstracts = fetch_pubmed_abstracts(pmids)
        if not abstracts or len(abstracts) < 200:
            print(f"  ⚠ {search['title']}: insufficient abstract data")
            continue

        # Format and save
        content = format_pubmed_guideline(search["title"], search["query"], abstracts)
        with open(filepath, "w") as f:
            f.write(content)

        print(f"  ✅ {search['title']}: {len(pmids)} articles saved ({len(content)} chars)")
        fetched += 1
        time.sleep(0.5)  # Rate limit

    print(f"\n  Fetched {fetched} guideline collections from PubMed")
    return fetched


# ═══════════════════════════════════════════
# Main
# ═══════════════════════════════════════════

def main():
    print("=" * 60)
    print("  External Clinical Guideline Fetcher")
    print("  Sources: OpenFDA + PubMed (NCBI)")
    print("=" * 60)

    drug_count = fetch_all_drug_labels()
    pubmed_count = fetch_all_pubmed_guidelines()

    # Count total guidelines
    total = len([f for f in os.listdir(GUIDELINES_DIR) if f.endswith(".md")])

    print("\n" + "=" * 60)
    print(f"  FETCH COMPLETE")
    print(f"  Drug labels fetched: {drug_count}")
    print(f"  PubMed guidelines fetched: {pubmed_count}")
    print(f"  Total guidelines in corpus: {total}")
    print("=" * 60)


if __name__ == "__main__":
    main()
