# Clinical Co-Pilot — Evaluation Results

**Date:** May 9, 2026
**Suite:** `agent/eval_clinical_graph.py` (W2, 58 boolean-rubric cases)
**Total: 58/58 passing (100.0%)** in **610.9s** (~10.2 min)
**Baseline gate: pass**

The full per-case JSON lives in [`agent/eval_clinical_results.json`](agent/eval_clinical_results.json).
CI runs the same suite on every push to `agent/**` — see
`.github/workflows/agent-evals.yml`.

---

## Per-bucket pass counts

| Bucket | Cases | Pass | What it tests |
|---|---|---|---|
| `schema_valid` | 10 | **10/10** | `extract_document()` returns expected verbatim values from each sample lab/intake doc. LLM (VLM, temp 0). |
| `citation_present` | 10 | **10/10** | `derived_fact_citations` rows exist for every fact-bearing table for the 4 ingested patients; data-store boundary holds (C-10 walks the import graph). |
| `factually_consistent` | 10 | **10/10** | Top-1 retrieved file matches expected; agent acknowledges absent values rather than fabricating. |
| `safe_refusal` | 10 | **10/10** | Agent declines unsafe / out-of-scope prompts (jailbreak, off-topic, "write a prescription", "order a surgery", unsafe doses). |
| `no_phi_in_logs` | 10 | **10/10** | Encounter logs scrub PHI (names, DOB, phone, ZIP); required structured fields (tool_sequence, latency_per_step_ms, tokens_used, cost_estimate_usd, retrieval_hits, eval_outcome) are present. |
| `evidence_separation` | 8 | **8/8** | In-scope clinical-management questions yield three-section answers (CHART FINDINGS / EVIDENCE / CONSIDERATIONS) without sentence-leading imperatives. Catches the soft over-recommendation pattern that `safe_refusal` misses. |

---

## Baseline / regression gate

`agent/eval_baseline.json` pins the per-bucket pass-count baseline plus an
absolute `min_threshold` floor. The runner exits **1** if any bucket drops
**>5%** from baseline OR falls **below `min_threshold`**. Same gate applies
to the total. CI uses the same exit code, so any meaningful regression
fails the build and blocks merge.

```json
{
  "by_category": {
    "schema_valid":        {"baseline": 10, "min_threshold": 8},
    "citation_present":    {"baseline": 10, "min_threshold": 8},
    "factually_consistent":{"baseline": 10, "min_threshold": 8},
    "safe_refusal":        {"baseline": 10, "min_threshold": 8},
    "no_phi_in_logs":      {"baseline": 10, "min_threshold": 8},
    "evidence_separation": {"baseline":  8, "min_threshold": 6}
  },
  "total": {"baseline": 58, "min_threshold": 51}
}
```

---

## Latency progression across recent runs

Tracked because it's the second-biggest reviewer feedback item.

| Run | Total time | What changed |
|---|---|---|
| W2 baseline (all-Sonnet) | ~770s | initial 50-case suite |
| Post-tightening (mgmt answers) | 690s | shorter answers (4400→1800 chars) |
| Haiku for routing | 690s | supervisor calls 3.0s → 1.0s each |
| Latest | **611s** | warm cache + tightened budgets |

F-07 (Whitaker BNP-not-in-chart) — the original pathological case at 8070s
on the unbounded baseline — now consistently runs in **~12s** under the
60s SDK timeout + 120s end-to-end budget.

---

## How to reproduce

Locally (~10 min, requires `agent/.env` with `ANTHROPIC_API_KEY`):

```sh
cd agent
. .venv/bin/activate
python3 eval_clinical_graph.py
```

In CI: every push to `agent/**` triggers `.github/workflows/agent-evals.yml`,
which spins up MariaDB + OpenEMR, seeds the 4 W2 patients, runs the full
suite, and uploads `eval_clinical_results.json` as a build artifact.
