#!/usr/bin/env python3
"""Aggregate the full-dataset replay (run_full.py output) into tables.

Reads ROOT/results/<unit>/<policy>/summary.json, the per-unit conversion stats
(ROOT/traces/<unit>.stats.json) and ROOT/units/windows.json. A run replayed as
consecutive trial slices (units chunk-<run>-cNN) is recombined when its full
replay is missing: requests, tokens and SLA counts are summed, TTFT and ITL p99
take the worst slice, and trial-time medians take the median of slice medians. Writes OUT/units.csv (one row per unit and policy),
OUT/aggregate.json and OUT/RESULTS.md. Run units (leaderboard runs) and
endpoint windows are reported separately so no request is counted twice.
A replay meets the SLA when at least 99% of its requests meet the configured
TTFT and inter-token bounds (AISimulate's goodput count).
"""
import argparse, csv, json, os, statistics as st
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(os.environ.get("FULL_ROOT", "full"))
POLICIES = ["rr", "kv", "kvp16", "aff"]
LABEL = {"rr": "Round-robin", "kv": "KV router (defaults)", "kvp16": "KV router, prefill_load_scale 16",
         "aff": "KV router + session affinity"}
SLA_SHARE = 0.99


def family(served):
    s = served.lower()
    for key, name in (("glm-5.3-flash", "GLM-5.3-Flash (zai-org)"), ("deepseek-v4.1-flash", "DeepSeek-V4.1-Flash"),
                      ("flint", "flint"), ("ripple", "Ripple-65B-Preview")):
        if key in s:
            return name
    return served


def recombine(rows):
    """Replace a run with its recombined slices when any of its four full replays is missing.

    Returns (rows, checks): checks pairs full and sliced results for runs that have both.
    """
    have = defaultdict(set)
    for r in rows:
        if r["kind"] == "run":
            have[r["unit"]].add(r["policy"])
    complete_full = {u for u, ps in have.items() if all(p in ps for p in POLICIES)}
    chunks = defaultdict(list)
    for r in rows:
        if r["kind"] == "chunk":
            parent = r["unit"].removeprefix("chunk-").rsplit("-c", 1)[0]
            chunks[(parent, r["policy"])].append(r)
    sliced_parents = {k[0] for k in chunks}
    out = [r for r in rows if r["kind"] != "chunk" and not (r["kind"] == "run" and r["unit"] in sliced_parents
                                                            and r["unit"] not in complete_full)]
    checks = []
    expected = defaultdict(int)
    for p in (ROOT / "units").glob("chunk-*.jsonl.gz"):
        expected[p.name.removeprefix("chunk-").rsplit("-c", 1)[0]] += 1
    for (parent, policy), cs in chunks.items():
        if len(cs) < expected[parent]:
            continue
        req = sum(c["requests"] for c in cs); inp = sum(c["inputTokens"] for c in cs)
        r = dict(cs[0], unit=parent, kind="run", replayedAs=f"{len(cs)} slices", plays=sum(c["plays"] for c in cs), requests=req,
                 peakTrials=max(c["peakTrials"] for c in cs), inputTokens=inp,
                 providerCachedRatio=sum(c["providerCachedRatio"] * c["inputTokens"] for c in cs) / inp,
                 traceReuseRatio=sum(c["traceReuseRatio"] * c["inputTokens"] for c in cs) / inp,
                 prefixReuse=sum(c["prefixReuse"] * c["inputTokens"] for c in cs) / inp,
                 prefillTokens=sum(c["prefillTokens"] for c in cs),
                 ttftMean=sum(c["ttftMean"] * c["requests"] for c in cs) / req, ttftP99=max(c["ttftP99"] for c in cs),
                 itlMean=sum(c["itlMean"] * c["requests"] for c in cs) / req, itlP99=max(c["itlP99"] for c in cs),
                 goodput=sum(c["goodput"] for c in cs), completed=sum(c["completed"] for c in cs),
                 trialP50Min=st.median(c["trialP50Min"] for c in cs), trialP90Min=st.median(c["trialP90Min"] for c in cs),
                 gpuHours=sum(c["gpuHours"] for c in cs), wallSeconds=max(c["wallSeconds"] for c in cs))
        r["goodputShare"] = r["goodput"] / req
        if parent in complete_full:
            f = next(x for x in rows if x["kind"] == "run" and x["unit"] == parent and x["policy"] == policy)
            checks.append(dict(unit=parent, policy=policy, fullReuse=f["prefixReuse"], slicedReuse=r["prefixReuse"],
                               fullPrefill=f["prefillTokens"], slicedPrefill=r["prefillTokens"],
                               fullGoodput=f["goodputShare"], slicedGoodput=r["goodputShare"],
                               fullTtftP99=f["ttftP99"], slicedTtftP99=r["ttftP99"]))
        else:
            out.append(r)
    return out, checks


def pct(x):
    return f"{x:.1%}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "aggregate"))
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    stats = {p.name.removesuffix(".stats.json"): json.loads(p.read_text()) for p in (ROOT / "traces").glob("*.stats.json")}
    windows = {w["unit"]: w for w in json.loads((ROOT / "units" / "windows.json").read_text())}

    rows = []
    for unit_dir in sorted((ROOT / "results").iterdir()):
        for p in POLICIES:
            f = unit_dir / p / "summary.json"
            if not f.exists():
                continue
            s = json.loads(f.read_text())
            u = s["unit"]
            us = stats[u]
            by = us.get("byHarness") or {}
            top = max(by, key=lambda k: by[k]["calls"]) if by else "?|?"
            harness, served = top.split("|", 1)
            gpus_per_worker = 4 if u.startswith("dsvcheck-") else 2
            rows.append(dict(
                unit=u, kind=("window" if u.startswith("endpoint-") else "dsvcheck" if u.startswith("dsvcheck-")
                              else "chunk" if u.startswith("chunk-") else "run"),
                policy=p, family=family(served), harness=harness, plays=us["plays"], requests=us["requests"],
                peakTrials=us["peakConcurrentPlays"], workers=s["workers"], gpus=s["workers"] * gpus_per_worker,
                inputTokens=us["inputTokens"], providerCachedRatio=us["providerCachedRatio"],
                traceReuseRatio=us["traceReuseRatio"], prefixReuse=s["prefix_cache_reused_ratio"],
                prefillTokens=s["committed_prefill_tokens"], ttftMean=s["mean_ttft_ms"], ttftP99=s["p99_ttft_ms"],
                itlMean=s["mean_itl_ms"], itlP99=s["p99_itl_ms"], goodputShare=s["goodput_completed_requests"] / s["num_requests"],
                completed=s["completed_requests"], trialP50Min=s["p50_trajectory_e2e_latency_ms"] / 60000,
                trialP90Min=s["p90_trajectory_e2e_latency_ms"] / 60000, gpuHours=s["gpu_hours"], wallSeconds=s["wallSeconds"],
                goodput=s["goodput_completed_requests"], replayedAs="full"))
    rows, checks = recombine(rows)
    (out / "slice-check.json").write_text(json.dumps(checks, indent=1))
    with open(out / "units.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)

    def block(sel):
        """Totals per policy over units that have all four policies."""
        units = defaultdict(dict)
        for r in sel:
            units[r["unit"]][r["policy"]] = r
        full = {u: d for u, d in units.items() if all(p in d for p in POLICIES)}
        res = {}
        for p in POLICIES:
            rs = [d[p] for d in full.values()]
            if not rs:
                continue
            inp = sum(r["inputTokens"] for r in rs)
            res[p] = dict(
                units=len(rs), requests=sum(r["requests"] for r in rs), trials=sum(r["plays"] for r in rs),
                prefillTokens=sum(r["prefillTokens"] for r in rs),
                prefixReuse=sum(r["prefixReuse"] * r["inputTokens"] for r in rs) / inp,
                unitsMeetingSla=sum(r["goodputShare"] >= SLA_SHARE for r in rs),
                requestsMeetingSla=sum(r["goodputShare"] * r["requests"] for r in rs) / sum(r["requests"] for r in rs),
                ttftMeanWeighted=sum(r["ttftMean"] * r["requests"] for r in rs) / sum(r["requests"] for r in rs),
                medianUnitTtftP99=st.median(r["ttftP99"] for r in rs),
                worstUnitTtftP99=max(r["ttftP99"] for r in rs),
                medianTrialP50Min=st.median(r["trialP50Min"] for r in rs),
                gpuHours=sum(r["gpuHours"] for r in rs), providerCachedRatio=sum(r["providerCachedRatio"] * r["inputTokens"] for r in rs) / inp)
        ratios = {}
        for p in ("rr", "kv", "kvp16"):
            vals = [d[p]["prefillTokens"] / d["aff"]["prefillTokens"] for d in full.values() if d["aff"]["prefillTokens"]]
            if vals:
                ratios[p] = dict(median=st.median(vals), p90=sorted(vals)[int(0.9 * (len(vals) - 1))])
        slas = Counter()
        for d in full.values():
            key = "".join("Y" if d[p]["goodputShare"] >= SLA_SHARE else "n" for p in POLICIES)
            slas[key] += 1
        return dict(policies=res, prefillVsAffinity=ratios, slaPatterns=dict(slas), units=sorted(full))

    runs = [r for r in rows if r["kind"] == "run"]
    agg = dict(all=block(runs), byFamily={}, byHarness={}, windows=block([r for r in rows if r["kind"] == "window"]),
               dsvcheck=block([r for r in rows if r["kind"] == "dsvcheck"]))
    for fam in sorted({r["family"] for r in runs}):
        agg["byFamily"][fam] = block([r for r in runs if r["family"] == fam])
    for h in sorted({r["harness"] for r in runs}):
        agg["byHarness"][h] = block([r for r in runs if r["harness"] == h])
    (out / "aggregate.json").write_text(json.dumps(agg, indent=1))

    L = ["# Full-dataset Dynamo replay", ""]
    a0 = agg["all"]["policies"]
    if a0:
        n = a0["aff"]
        L += [f"{n['units']} leaderboard runs, {n['trials']:,} trials, {n['requests']:,} requests per router. "
              f"A replay meets the SLA when at least {SLA_SHARE:.0%} of its requests meet 2 s TTFT and 50 ms inter-token latency.", ""]
        sliced = sorted({r["unit"] for r in runs if r.get("replayedAs", "full") != "full"})
        if sliced:
            L += [f"{len(sliced)} {'run was' if len(sliced) == 1 else 'runs were'} replayed as consecutive trial slices and recombined: " + ", ".join(f"`{u}`" for u in sliced) + ".", ""]

    def table(title, blk):
        pol = blk["policies"]
        if not pol:
            return
        L.extend([f"## {title}", "",
                  "| Router | Prefix reuse | Prefill tokens | Runs meeting SLA | Requests meeting SLA | Mean TTFT | Median run p99 TTFT | Worst run p99 TTFT | Median trial p50 | GPU-hours |",
                  "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"])
        for p in POLICIES:
            if p not in pol:
                continue
            x = pol[p]
            L.append(f"| {LABEL[p]} | {pct(x['prefixReuse'])} | {x['prefillTokens'] / 1e9:,.2f}B | {x['unitsMeetingSla']} of {x['units']} "
                     f"| {pct(x['requestsMeetingSla'])} | {x['ttftMeanWeighted']:,.0f} ms | {x['medianUnitTtftP99']:,.0f} ms "
                     f"| {x['worstUnitTtftP99'] / 1000:,.1f} s | {x['medianTrialP50Min']:.1f} min | {x['gpuHours']:,.0f} |")
        r = blk["prefillVsAffinity"]
        if r:
            L.append("")
            L.append("Prefill relative to affinity, per run (median / p90): " + "; ".join(
                f"{LABEL[p]} {v['median']:.2f}x / {v['p90']:.2f}x" for p, v in r.items()) + ".")
        L.append(f"Provider cached share over the same runs: {pct(pol['aff']['providerCachedRatio'])}.")
        pats = blk["slaPatterns"]
        if len(pats) > 1:
            L.append("")
            L.append("SLA outcomes per run (Y meets, n misses; order: round-robin, KV router, KV with prefill_load_scale 16, affinity): "
                     + ", ".join(f"{k} {v}" for k, v in sorted(pats.items(), key=lambda kv: -kv[1])) + ".")
        L.append("")

    table("All leaderboard runs", agg["all"])
    for fam, blk in agg["byFamily"].items():
        table(f"Traffic from {fam}", blk)
    L += ["## By harness (prefill tokens, billions; runs meeting SLA)", "",
          "| Harness | Runs | Requests | Round-robin | KV router | KV, prefill_load_scale 16 | Affinity |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for h, blk in agg["byHarness"].items():
        pol = blk["policies"]
        if not pol:
            continue
        cells = [f"{pol[p]['prefillTokens'] / 1e9:.2f} ({pol[p]['unitsMeetingSla']})" for p in POLICIES]
        L.append(f"| {h} | {pol['aff']['units']} | {pol['aff']['requests']:,} | " + " | ".join(cells) + " |")
    L.append("")
    if checks:
        L += ["## Slice check", "",
              "Runs with both a full replay and a recombined six-slice replay. Slicing drops the overlap between trials at slice boundaries.", "",
              "| Run | Router | Prefix reuse full / sliced | Prefill full / sliced | Requests meeting SLA full / sliced | p99 TTFT full / sliced |",
              "| --- | --- | ---: | ---: | ---: | ---: |"]
        for c in sorted(checks, key=lambda c: (c["unit"], POLICIES.index(c["policy"]))):
            L.append(f"| `{c['unit']}` | {LABEL[c['policy']]} | {pct(c['fullReuse'])} / {pct(c['slicedReuse'])} "
                     f"| {c['fullPrefill'] / 1e6:,.0f}M / {c['slicedPrefill'] / 1e6:,.0f}M | {pct(c['fullGoodput'])} / {pct(c['slicedGoodput'])} "
                     f"| {c['fullTtftP99']:,.0f} / {c['slicedTtftP99']:,.0f} ms |")
        L.append("")
    table("Endpoint windows (concurrent runs merged per endpoint)", agg["windows"])
    table("DeepSeek-V4.1-Flash native cross-check", agg["dsvcheck"])
    (out / "RESULTS.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
