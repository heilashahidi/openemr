"""
Eval Latency Analysis
Reads eval_results.json and rag_test_results.json and surfaces latency insights.
Run: python3 analyze_evals.py
"""

import json

def load_results(filename):
    try:
        with open(filename) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"  ⚠ {filename} not found")
        return None

def analyze(results, label):
    tests = results.get("results", [])
    if not tests:
        return

    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"  {len(tests)} tests | {results['summary']['pass_rate']} pass rate")
    print(f"{'='*70}")

    # Sort by latency
    by_latency = sorted(tests, key=lambda t: t.get("elapsed", 0), reverse=True)

    # Top 5 slowest
    print(f"\n  🐢 SLOWEST QUERIES:")
    print(f"  {'ID':<10} {'Time':>6}  {'Tools':>5}  {'Tokens':>7}  Name")
    print(f"  {'-'*10} {'-'*6}  {'-'*5}  {'-'*7}  {'-'*30}")
    for t in by_latency[:5]:
        tools = len(t.get("tools_called", []))
        print(f"  {t['id']:<10} {t['elapsed']:>5.1f}s  {tools:>5}  {t.get('tokens', 0):>7}  {t['name'][:40]}")

    # Top 5 fastest
    print(f"\n  🚀 FASTEST QUERIES:")
    print(f"  {'ID':<10} {'Time':>6}  {'Tools':>5}  {'Tokens':>7}  Name")
    print(f"  {'-'*10} {'-'*6}  {'-'*5}  {'-'*7}  {'-'*30}")
    for t in by_latency[-5:]:
        tools = len(t.get("tools_called", []))
        print(f"  {t['id']:<10} {t['elapsed']:>5.1f}s  {tools:>5}  {t.get('tokens', 0):>7}  {t['name'][:40]}")

    # Latency by tool count
    tool_buckets = {}
    for t in tests:
        tools = len(t.get("tools_called", []))
        if tools not in tool_buckets:
            tool_buckets[tools] = []
        tool_buckets[tools].append(t["elapsed"])

    print(f"\n  📊 LATENCY BY TOOL COUNT:")
    print(f"  {'Tools':>5}  {'Count':>5}  {'Avg':>6}  {'Min':>6}  {'Max':>6}")
    print(f"  {'-'*5}  {'-'*5}  {'-'*6}  {'-'*6}  {'-'*6}")
    for tools in sorted(tool_buckets.keys()):
        times = tool_buckets[tools]
        avg = sum(times) / len(times)
        print(f"  {tools:>5}  {len(times):>5}  {avg:>5.1f}s  {min(times):>5.1f}s  {max(times):>5.1f}s")

    # Latency by tool type
    tool_latency = {}
    for t in tests:
        for tool in t.get("tools_called", []):
            if isinstance(tool, str):
                tool_name = tool
            else:
                tool_name = tool.get("tool", "unknown")
            if tool_name not in tool_latency:
                tool_latency[tool_name] = []
            tool_latency[tool_name].append(t["elapsed"])

    print(f"\n  🔧 LATENCY BY TOOL TYPE:")
    print(f"  {'Tool':<25}  {'Used':>4}  {'Avg Time':>8}")
    print(f"  {'-'*25}  {'-'*4}  {'-'*8}")
    for tool, times in sorted(tool_latency.items(), key=lambda x: sum(x[1])/len(x[1]), reverse=True):
        avg = sum(times) / len(times)
        print(f"  {tool:<25}  {len(times):>4}  {avg:>7.1f}s")

    # Token efficiency
    print(f"\n  💰 TOKEN ANALYSIS:")
    tokens = [t.get("tokens", 0) for t in tests]
    total = sum(tokens)
    avg = total / len(tokens) if tokens else 0
    print(f"  Total tokens: {total:,}")
    print(f"  Avg per query: {avg:,.0f}")
    print(f"  Most expensive: {by_latency[0]['id']} ({max(tokens):,} tokens)")
    cheapest = min(tests, key=lambda t: t.get("tokens", 0))
    print(f"  Cheapest: {cheapest['id']} ({cheapest.get('tokens', 0):,} tokens)")

    # Cost estimate
    cost_per_token = 0.000003  # ~$3/1M tokens for Sonnet input
    print(f"  Est. cost (all tests): ${total * cost_per_token:.2f}")
    print(f"  Est. cost per query: ${avg * cost_per_token:.4f}")

    # Correlation
    print(f"\n  📈 LATENCY DRIVERS:")
    high_lat = [t for t in tests if t["elapsed"] > 10]
    low_lat = [t for t in tests if t["elapsed"] < 5]
    if high_lat:
        avg_tools_high = sum(len(t.get("tools_called", [])) for t in high_lat) / len(high_lat)
        avg_tokens_high = sum(t.get("tokens", 0) for t in high_lat) / len(high_lat)
        print(f"  Queries >10s: {len(high_lat)} — avg {avg_tools_high:.1f} tools, avg {avg_tokens_high:.0f} tokens")
    if low_lat:
        avg_tools_low = sum(len(t.get("tools_called", [])) for t in low_lat) / len(low_lat)
        avg_tokens_low = sum(t.get("tokens", 0) for t in low_lat) / len(low_lat)
        print(f"  Queries <5s:  {len(low_lat)} — avg {avg_tools_low:.1f} tools, avg {avg_tokens_low:.0f} tokens")
    print(f"  → Primary driver: tool count. Each tool adds ~1-2s (FHIR call + LLM reasoning turn).")


def main():
    print("=" * 70)
    print("  Clinical Co-Pilot — Eval Latency & Cost Analysis")
    print("=" * 70)

    eval_data = load_results("eval_results.json")
    rag_data = load_results("rag_test_results.json")

    if eval_data:
        analyze(eval_data, "CORE EVAL SUITE (eval_results.json)")
    if rag_data:
        analyze(rag_data, "RAG TEST SUITE (rag_test_results.json)")

    # Combined summary
    if eval_data and rag_data:
        all_tests = eval_data["results"] + rag_data["results"]
        total_time = sum(t["elapsed"] for t in all_tests)
        total_tokens = sum(t.get("tokens", 0) for t in all_tests)
        total_passed = sum(1 for t in all_tests if t["passed"])

        print(f"\n{'='*70}")
        print(f"  COMBINED SUMMARY")
        print(f"{'='*70}")
        print(f"  Tests: {total_passed}/{len(all_tests)} passed ({total_passed/len(all_tests)*100:.1f}%)")
        print(f"  Total time: {total_time:.1f}s")
        print(f"  Total tokens: {total_tokens:,}")
        print(f"  Est. total cost: ${total_tokens * 0.000003:.2f}")
        print(f"  Avg latency: {total_time/len(all_tests):.1f}s per query")
        print(f"{'='*70}")


if __name__ == "__main__":
    main()
