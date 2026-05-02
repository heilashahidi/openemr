"""
Clinical Co-Pilot — RAG + Hybrid Retrieval Test Suite
Tests semantic search over clinical notes combined with structured FHIR tools.
Run: python3 test_rag.py
Outputs: rag_test_results.json
"""

import requests
import json
import time
import sys

AGENT_URL = "http://localhost:8000"

PATIENTS = {
    "sarah": "a1a5b7d7-bac2-4eb8-b471-96f0eadb219e",
    "philip": "a1a5b82c-a50b-4e0d-b86f-4d7d216f6c27",
    "candy": "a1a5b8f9-7933-44a5-bad1-b4fdf8381d57",
    "robert": "a1a9fb05-f4c5-484e-bcc6-5bfaa9218be1",
    "maria": "a1a9fb05-f4c8-4e18-bf81-76dc9b8aa163",
    "james": "a1a9fb05-f4cb-4b9c-b9ed-ae7a03fc8389",
    "emily": "a1a9fb05-f4cd-49e2-8090-e9720effcc4b",
    "david": "fbaa4958-437f-11f1-9821-62123fdb3c0f",
    "angela": "fc6aeb54-437f-11f1-9821-62123fdb3c0f",
}

TESTS = [
    # ── RAG-only tests ──
    {
        "id": "RAG-01",
        "name": "David: chest pain or swelling history",
        "patient": "david",
        "message": "Has this patient ever mentioned chest pain or swelling?",
        "expect_tool": "search_notes",
        "expect_content": ["swelling", "leg"],
    },
    {
        "id": "RAG-02",
        "name": "Angela: sleep or insomnia discussed",
        "patient": "angela",
        "message": "Has sleep or insomnia ever been discussed with this patient?",
        "expect_tool": "search_notes",
        "expect_content": ["not sleeping", "sleep"],
    },
    {
        "id": "RAG-03",
        "name": "Sarah: vision problems (silence)",
        "patient": "sarah",
        "message": "Has this patient ever mentioned vision problems or blurry vision?",
        "expect_tool": "search_notes",
        "expect_content": ["no", "not"],
    },
    {
        "id": "RAG-04",
        "name": "David: numbness or tingling in feet",
        "patient": "david",
        "message": "Has this patient ever had numbness or tingling in their feet?",
        "expect_tool": "search_notes",
        "expect_content": ["numbness", "neuropathy"],
    },
    {
        "id": "RAG-05",
        "name": "Angela: feeling overwhelmed or anxious",
        "patient": "angela",
        "message": "Has this patient mentioned feeling overwhelmed or anxious?",
        "expect_tool": "search_notes",
        "expect_content": ["overwhelmed"],
    },
    {
        "id": "RAG-06",
        "name": "Emily: headaches (sparse chart)",
        "patient": "emily",
        "message": "Has this patient ever mentioned headaches?",
        "expect_tool": "search_notes",
        "expect_content": ["headaches", "3 months"],
    },
    {
        "id": "RAG-07",
        "name": "Angela: lupus flares recently",
        "patient": "angela",
        "message": "Has this patient had any lupus flares recently? What triggered them?",
        "expect_tool": "search_notes",
        "expect_content": ["joint pain", "rash", "cheeks"],
    },
    {
        "id": "RAG-08",
        "name": "Philip: breathing getting worse",
        "patient": "philip",
        "message": "Has this patient's breathing been getting worse?",
        "expect_tool": "search_notes",
        "expect_content": ["shortness of breath", "worsening"],
    },

    # ── Hybrid tests (RAG + structured) ──
    {
        "id": "HYB-01",
        "name": "David: leg swelling history explanation",
        "patient": "david",
        "message": "This patient is here for leg swelling. What in their history might explain it?",
        "expect_tool": "search_notes",
        "expect_also": ["get_active_conditions"],
        "expect_content": ["heart failure", "furosemide"],
    },
    {
        "id": "HYB-02",
        "name": "Candy: stomach bothering her",
        "patient": "candy",
        "message": "This patient says her stomach has been bothering her. What do we know about that?",
        "expect_tool": "search_notes",
        "expect_content": ["irritable bowel", "stomach", "bloating"],
    },
    {
        "id": "HYB-03",
        "name": "David: kidney function trending",
        "patient": "david",
        "message": "What do we know about this patient's kidney function? Has it been getting worse?",
        "expect_tool": "search_notes",
        "expect_content": ["kidney", "chronic kidney"],
    },
    {
        "id": "HYB-04",
        "name": "Angela: depression management",
        "patient": "angela",
        "message": "How has this patient's depression been managed? Any recent changes?",
        "expect_tool": "search_notes",
        "expect_content": ["depression", "duloxetine"],
    },
    {
        "id": "HYB-05",
        "name": "Maria: exercise or physical activity issues",
        "patient": "maria",
        "message": "Has this patient mentioned any issues with exercise or physical activity?",
        "expect_tool": "search_notes",
        "expect_content": ["back pain", "unable to exercise"],
    },
    {
        "id": "HYB-06",
        "name": "David: eye issues documented",
        "patient": "david",
        "message": "Any eye issues documented for this patient?",
        "expect_tool": "search_notes",
        "expect_content": ["retinopathy", "eye"],
    },
    {
        "id": "HYB-07",
        "name": "David: blood thinners and bleeding",
        "patient": "david",
        "message": "Is this patient on any blood thinners and have they had any bleeding issues?",
        "expect_tool": "search_notes",
        "expect_also": ["get_active_medications"],
        "expect_content": ["apixaban", "aspirin"],
    },
    {
        "id": "HYB-08",
        "name": "Candy: migraine visit frequency",
        "patient": "candy",
        "message": "How often has this patient come in for migraine-related visits?",
        "expect_tool": "search_notes",
        "expect_content": ["migraine"],
    },

    # ── Silence tests ──
    {
        "id": "SIL-01",
        "name": "Emily: diabetes history (should be empty)",
        "patient": "emily",
        "message": "Has this patient ever been told they have diabetes?",
        "expect_tool": "search_notes",
        "expect_content": ["no", "not"],
        "must_not_contain": ["diagnosed with diabetes", "type 2 diabetes", "metformin"],
    },
    {
        "id": "SIL-02",
        "name": "Sarah: surgery history (should be empty)",
        "patient": "sarah",
        "message": "Has this patient ever had any surgeries?",
        "expect_tool": "search_notes",
        "expect_content": ["no", "not"],
        "must_not_contain": ["surgery was performed", "underwent surgery"],
    },
]


def run_test(test):
    patient_id = PATIENTS.get(test["patient"], "")
    start = time.time()

    try:
        resp = requests.post(
            f"{AGENT_URL}/chat",
            json={"patient_id": patient_id, "message": test["message"]},
            timeout=90,
        )
        elapsed = time.time() - start

        if resp.status_code != 200:
            return {"id": test["id"], "name": test["name"], "passed": False, "failures": [f"HTTP {resp.status_code}"], "elapsed": round(elapsed, 2)}

        data = resp.json()
        response = data.get("response", "")
        tools = [t["tool"] for t in data.get("tools_called", [])]
        failures = []

        # Check expected tool was called
        if test.get("expect_tool") and test["expect_tool"] not in tools:
            failures.append(f"Expected {test['expect_tool']} but got: {tools}")

        # Check additional expected tools
        if test.get("expect_also"):
            for t in test["expect_also"]:
                if t not in tools:
                    failures.append(f"Expected additional tool {t} not called")

        # Check expected content
        if test.get("expect_content"):
            response_lower = response.lower()
            if not any(w.lower() in response_lower for w in test["expect_content"]):
                failures.append(f"Missing expected content: {test['expect_content']}")

        # Check must not contain
        if test.get("must_not_contain"):
            response_lower = response.lower()
            for phrase in test["must_not_contain"]:
                if phrase.lower() in response_lower:
                    failures.append(f"Contains forbidden: '{phrase}'")

        return {
            "id": test["id"],
            "name": test["name"],
            "passed": len(failures) == 0,
            "failures": failures,
            "elapsed": round(elapsed, 2),
            "tools_called": tools,
            "citations": len(data.get("citations", [])),
            "tokens": data.get("tokens_used", {}).get("total", 0),
            "response": response,
        }

    except Exception as e:
        return {"id": test["id"], "name": test["name"], "passed": False, "failures": [str(e)], "elapsed": round(time.time() - start, 2)}


def main():
    print("=" * 70)
    print("  Clinical Co-Pilot — RAG + Hybrid Retrieval Tests")
    print(f"  {len(TESTS)} tests | RAG-only + Hybrid + Silence handling")
    print("=" * 70)

    try:
        requests.get(f"{AGENT_URL}/health", timeout=5)
        print(f"\n  Agent: online\n")
    except:
        print("\n  ERROR: Agent not running.")
        sys.exit(1)

    results = []
    categories = {"RAG": [], "HYB": [], "SIL": []}
    total_start = time.time()

    for i, test in enumerate(TESTS):
        prefix = test["id"].split("-")[0]
        print(f"  [{i+1}/{len(TESTS)}] {test['id']} | {test['name']}")

        result = run_test(test)
        results.append(result)
        categories[prefix].append(result)

        if result["passed"]:
            print(f"       ✅ PASS ({result['elapsed']}s) | Tools: {result.get('tools_called', [])} | Citations: {result.get('citations', 0)}")
        else:
            print(f"       ❌ FAIL ({result['elapsed']}s)")
            for f in result.get("failures", []):
                print(f"          → {f}")

    total_elapsed = round(time.time() - total_start, 2)
    total_passed = sum(1 for r in results if r["passed"])
    total_tokens = sum(r.get("tokens", 0) for r in results)

    cat_names = {"RAG": "RAG-Only", "HYB": "Hybrid (RAG+Structured)", "SIL": "Silence Handling"}

    print("\n" + "=" * 70)
    print("  RESULTS")
    print("=" * 70)
    print(f"\n  Overall: {total_passed}/{len(results)} passed")
    print(f"  Time: {total_elapsed}s | Tokens: {total_tokens}")
    print(f"\n  By Category:")
    for prefix, res in categories.items():
        p = sum(1 for r in res if r["passed"])
        bar = "█" * p + "░" * (len(res) - p)
        print(f"    {cat_names[prefix]:30s} {bar} {p}/{len(res)}")

    failed = [r for r in results if not r["passed"]]
    if failed:
        print(f"\n  Failed:")
        for r in failed:
            print(f"    {r['id']} | {r['name']}")
            for f in r.get("failures", []):
                print(f"      → {f}")

    output = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "total": len(results),
            "passed": total_passed,
            "failed": len(results) - total_passed,
            "pass_rate": f"{(total_passed/len(results)*100):.1f}%",
            "total_time": total_elapsed,
            "total_tokens": total_tokens,
        },
        "by_category": {
            cat_names[c]: {"passed": sum(1 for r in rs if r["passed"]), "total": len(rs)}
            for c, rs in categories.items()
        },
        "results": results,
    }

    with open("rag_test_results.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n  Results saved → rag_test_results.json")
    print("=" * 70)


if __name__ == "__main__":
    main()
