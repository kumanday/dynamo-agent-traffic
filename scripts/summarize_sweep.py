#!/usr/bin/env python3
"""Summarize AISimulate replay reports from sweep.sh output directories.

Each directory is named <trace>-w<workers>-<policy> and holds prediction.json.
Prints one markdown row per finished replay, grouped by trace, plus a JSON copy
of the selected summary fields.
"""
import argparse, json, re
from pathlib import Path

FIELDS = ["completed_requests", "num_requests", "incomplete_trajectories", "prefix_cache_reused_ratio",
          "committed_prefill_tokens", "mean_ttft_ms", "median_ttft_ms", "p90_ttft_ms", "p99_ttft_ms",
          "mean_itl_ms", "p99_itl_ms", "mean_e2e_latency_ms", "p99_e2e_latency_ms",
          "p50_trajectory_e2e_latency_ms", "p90_trajectory_e2e_latency_ms", "mean_trajectory_e2e_latency_ms",
          "duration_ms", "gpu_hours", "output_throughput_tok_s"]
POLICY = {"rr": "round-robin", "kv": "KV router", "aff": "KV router + session affinity"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sweep_dir")
    ap.add_argument("--json", help="write the selected fields to this path")
    a = ap.parse_args()
    rows = []
    for d in sorted(Path(a.sweep_dir).iterdir()):
        m = re.fullmatch(r"(.+)-w(\d+)-(rr|kv|aff|kvp\d+)", d.name)
        p = d / "prediction.json"
        if not m or not p.exists():
            continue
        s = json.loads(p.read_text())["summary"]
        rows.append(dict(trace=m[1], workers=int(m[2]), policy=m[3], **{k: s.get(k) for k in FIELDS}))
    order = lambda p: {"rr": 0, "kv": 1, "aff": 99}.get(p, 1 + int(p[3:]) if p.startswith("kvp") else 50)
    rows.sort(key=lambda r: (r["trace"], r["workers"], order(r["policy"])))
    print("| Trace | Workers (GPUs) | Router | Requests | Prefix reuse | Prefill tokens | TTFT mean / p90 / p99 (ms) "
          "| ITL mean / p99 (ms) | Trial time p50 / p90 (min) |")
    print("| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for r in rows:
        done = f"{r['completed_requests']:,}" + ("" if r["completed_requests"] == r["num_requests"] else f" of {r['num_requests']:,}")
        label = POLICY.get(r["policy"]) or f"KV router, prefill_load_scale {r['policy'][3:]}"
        print(f"| {r['trace']} | {r['workers']} ({2 * r['workers']}) | {label} | {done} "
              f"| {r['prefix_cache_reused_ratio']:.1%} | {r['committed_prefill_tokens'] / 1e6:,.1f}M "
              f"| {r['mean_ttft_ms']:,.0f} / {r['p90_ttft_ms']:,.0f} / {r['p99_ttft_ms']:,.0f} "
              f"| {r['mean_itl_ms']:.1f} / {r['p99_itl_ms']:.1f} "
              f"| {r['p50_trajectory_e2e_latency_ms'] / 60000:,.1f} / {r['p90_trajectory_e2e_latency_ms'] / 60000:,.1f} |")
    if a.json:
        Path(a.json).write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
