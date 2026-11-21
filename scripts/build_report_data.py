#!/usr/bin/env python3
"""Build the report page's data files (report/data/*.json) from the tables in results/.

Inputs: results/full/aggregate.json, units.csv, windows.json, index-summary.json, assemble-summary.json,
slice-check.json and endpoint-timeline.md, and results/pilot/sweep-summaries.json.
Each output is {"source": [...], "rows": [...]}. Values keep more digits than the page prints;
the page does the rounding.
"""
import csv, json, re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RES = REPO / "results"
OUT = REPO / "report" / "data"
ROUTERS = [("rr", "Round-robin"), ("kv", "KV router, defaults"), ("kvp16", "KV router, prefill_load_scale 16"),
           ("aff", "KV router with session affinity")]
FAMILIES = [("DeepSeek-V4.1-Flash", "family_deepseek", "DeepSeek-V4.1-Flash"),
            ("GLM-5.3-Flash (zai-org)", "family_glm", "GLM-5.3-Flash (zai-org)"),
            ("Ripple-65B-Preview", "family_ripple", "Ripple-65B-Preview"),
            ("flint", "family_flint", "flint"),
            ("Inkling-2-Small", "family_inkling", "Inkling-2-Small (Together)")]
SLA_SHARE = 0.99


def write(name, rows, inputs):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps({"source": inputs, "rows": rows}, indent=1) + "\n")
    print(name, len(rows))


agg = json.loads((RES / "full/aggregate.json").read_text())

# Routers: one row per scope and router.
FAMILIES = [f for f in FAMILIES if f[0] in agg["byFamily"]]
scopes = [("all", f'All {agg["all"]["policies"]["aff"]["units"]} runs', agg["all"]),
          ("windows", f'{agg["windows"]["policies"]["aff"]["units"]} endpoint windows', agg["windows"]),
          ("deepseek_native", "DeepSeek-V4.1-Flash native cross-check", agg["dsvcheck"])]
scopes += [(sid, label, agg["byFamily"][fam]) for fam, sid, label in FAMILIES]
rows = []
for sid, label, blk in scopes:
    pol = blk["policies"]
    for rid, rlabel in ROUTERS:
        x = pol[rid]
        ratio = blk["prefillVsAffinity"].get(rid, {"median": 1.0, "p90": 1.0})
        rows.append(dict(scope=sid, scope_label=label, router=rid, router_label=rlabel, units=x["units"],
                         requests=x["requests"], trials=x["trials"],
                         units_meeting_sla=x["unitsMeetingSla"], units_missing_sla=x["units"] - x["unitsMeetingSla"],
                         requests_meeting_sla_pct=round(100 * x["requestsMeetingSla"], 5),
                         prefix_reuse_pct=round(100 * x["prefixReuse"], 5), prefill_tokens_b=round(x["prefillTokens"] / 1e9, 6),
                         prefill_vs_affinity=round(x["prefillTokens"] / pol["aff"]["prefillTokens"], 4),
                         prefill_vs_affinity_run_median=round(ratio["median"], 4),
                         prefill_vs_affinity_run_p90=round(ratio["p90"], 4),
                         mean_ttft_ms=round(x["ttftMeanWeighted"], 3), median_unit_p99_ttft_ms=round(x["medianUnitTtftP99"], 3),
                         worst_unit_p99_ttft_ms=round(x["worstUnitTtftP99"], 3),
                         median_trial_p50_min=round(x["medianTrialP50Min"], 4), gpu_hours=round(x["gpuHours"]),
                         provider_cached_pct=round(100 * x["providerCachedRatio"], 5)))
write("routers", rows, ["results/full/aggregate.json"])

# Traffic source: one row per model family.
rows = []
for fam, sid, label in FAMILIES:
    pol = agg["byFamily"][fam]["policies"]
    rows.append(dict(traffic=label, runs=pol["aff"]["units"], requests=pol["aff"]["requests"],
                     sla_rr=pol["rr"]["unitsMeetingSla"], sla_kv=pol["kv"]["unitsMeetingSla"],
                     sla_kvp16=pol["kvp16"]["unitsMeetingSla"], sla_aff=pol["aff"]["unitsMeetingSla"],
                     kv_vs_aff_prefill=round(pol["kv"]["prefillTokens"] / pol["aff"]["prefillTokens"], 4),
                     provider_cached_pct=round(100 * pol["aff"]["providerCachedRatio"], 5),
                     aff_reuse_pct=round(100 * pol["aff"]["prefixReuse"], 5)))
write("traffic", rows, ["results/full/aggregate.json"])

# Harness: one row per harness version. A run belongs to the harness that made most of its calls.
rows = []
for h, blk in agg["byHarness"].items():
    pol = blk["policies"]
    if not pol:
        continue
    rows.append(dict(harness=h, runs=pol["aff"]["units"], requests=pol["aff"]["requests"],
                     sla_rr=pol["rr"]["unitsMeetingSla"], sla_kv=pol["kv"]["unitsMeetingSla"],
                     sla_kvp16=pol["kvp16"]["unitsMeetingSla"], sla_aff=pol["aff"]["unitsMeetingSla"],
                     prefill_rr_b=round(pol["rr"]["prefillTokens"] / 1e9, 6), prefill_kv_b=round(pol["kv"]["prefillTokens"] / 1e9, 6),
                     prefill_kvp16_b=round(pol["kvp16"]["prefillTokens"] / 1e9, 6), prefill_aff_b=round(pol["aff"]["prefillTokens"] / 1e9, 6),
                     kv_vs_aff_prefill=round(pol["kv"]["prefillTokens"] / pol["aff"]["prefillTokens"], 4)))
rows.sort(key=lambda r: -r["requests"])
write("harness", rows, ["results/full/aggregate.json"])

# Runs and endpoint windows: one row per unit, the four routers side by side.
per = {"run": {}, "window": {}}
native, replays = {}, 0
with open(RES / "full/units.csv") as f:
    for r in csv.DictReader(f):
        if r["kind"] == "dsvcheck":
            native[r["policy"]] = r
        if r["kind"] not in per:
            continue
        replays += 1
        d = per[r["kind"]].setdefault(r["unit"], dict(unit=r["unit"], traffic=r["family"], harness=r["harness"],
                                                     trials=int(r["plays"]), peak_trials=int(r["peakTrials"]),
                                                     requests=int(r["requests"]), workers=int(r["workers"]),
                                                     gpus=int(r["gpus"]), replayed_as=r["replayedAs"]))
        p = r["policy"]
        d[f"prefill_{p}_tokens"] = int(r["prefillTokens"])
        d[f"sla_share_{p}_pct"] = round(100 * float(r["goodputShare"]), 4)
        d[f"sla_{p}"] = "meets" if float(r["goodputShare"]) >= SLA_SHARE else "misses"
        d[f"ttft_p99_{p}_ms"] = round(float(r["ttftP99"]), 2)
# A run ID starts with the date and time the leaderboard gave it (UTC), which the page plots as the run's date.
for d in per["run"].values():
    m = re.match(r"(\d{4})(\d\d)(\d\d)-", d["unit"])
    d["id_date"] = f"{m[1]}-{m[2]}-{m[3]}" if m else None
for kind in per:
    for d in per[kind].values():
        d["kv_vs_aff_prefill"] = round(d["prefill_kv_tokens"] / d["prefill_aff_tokens"], 3) if d["prefill_aff_tokens"] else None
write("runs", sorted(per["run"].values(), key=lambda r: r["unit"]), ["results/full/units.csv"])

win = {w["unit"]: w for w in json.loads((RES / "full/windows.json").read_text())}
rows = []
for u, d in sorted(per["window"].items(), key=lambda kv: (win[kv[0]]["endpoint"], win[kv[0]]["start"])):
    w = win[u]
    rows.append(dict(d, endpoint=w["endpoint"], merged_runs=len(w["runs"]), start_unix=w["start"], end_unix=w["end"],
                     hours=round((w["end"] - w["start"]) / 3600, 1)))
write("windows", rows, ["results/full/units.csv", "results/full/windows.json"])

# Native cross-check: the one run replayed on simulated DeepSeek-V4.1-Flash, next to the same run on the
# GLM-5.3-Flash target that every other result uses.
rows = []
for rid, rlabel in ROUTERS:
    n = native[rid]
    run = n["unit"].removeprefix("dsvcheck-")
    g = per["run"][run]
    rows.append(dict(router=rid, router_label=rlabel, run=run, trials=int(n["plays"]), requests=int(n["requests"]),
                     peak_trials=int(n["peakTrials"]), native_workers=int(n["workers"]), native_gpus=int(n["gpus"]),
                     native_prefill_tokens=int(n["prefillTokens"]),
                     native_prefill_vs_affinity=round(int(n["prefillTokens"]) / int(native["aff"]["prefillTokens"]), 4),
                     native_ttft_p99_ms=round(float(n["ttftP99"]), 3), native_itl_mean_ms=round(float(n["itlMean"]), 4),
                     native_sla_share_pct=round(100 * float(n["goodputShare"]), 4),
                     target_workers=g["workers"], target_gpus=g["gpus"], target_prefill_tokens=g[f"prefill_{rid}_tokens"],
                     target_prefill_vs_affinity=round(g[f"prefill_{rid}_tokens"] / g["prefill_aff_tokens"], 4),
                     target_ttft_p99_ms=g[f"ttft_p99_{rid}_ms"], target_sla_share_pct=g[f"sla_share_{rid}_pct"]))
write("native", rows, ["results/full/units.csv"])

# Pilot: two full runs and their 100-trial slices, by worker count and router.
TRACES = {"flint-hermes-upper": ("hermes_run", "Hermes run (flint)"), "glm-openclaw-upper": ("openclaw_run", "OpenClaw run (GLM-5.3-Flash)"),
          "glm-openclaw-lower": ("openclaw_run_lower", "OpenClaw run, lower-bound hashes"),
          "calib-hermes100": ("hermes_slice", "Hermes, first 100 trials"), "calib-glm100": ("openclaw_slice", "OpenClaw, first 100 trials")}
rows = []
for k, v in json.loads((RES / "pilot/sweep-summaries.json").read_text()).items():
    m = re.fullmatch(r"(.+)-w(\d+)-(rr|kv|aff|kvp\d+)", k)
    if not m or m[1] not in TRACES:
        continue
    s = v["summary"]
    tid, tlabel = TRACES[m[1]]
    rows.append(dict(trace=tid, trace_label=tlabel, workers=int(m[2]), gpus=2 * int(m[2]), router=m[3],
                     requests=s["num_requests"], completed_requests=s["completed_requests"],
                     prefix_reuse_pct=round(100 * s["prefix_cache_reused_ratio"], 5),
                     prefill_tokens_m=round(s["committed_prefill_tokens"] / 1e6, 4),
                     ttft_mean_ms=round(s["mean_ttft_ms"], 3), ttft_p99_ms=round(s["p99_ttft_ms"], 3),
                     itl_p99_ms=round(s["p99_itl_ms"], 3), median_trial_min=round(s["p50_trajectory_e2e_latency_ms"] / 60000, 4)))
rows.sort(key=lambda r: (r["trace"], r["workers"], r["router"]))
write("pilot", rows, ["results/pilot/sweep-summaries.json"])

# Flint endpoint timeline, 30-minute buckets, 2026-11-09 16:00 to 2026-11-10 06:00 UTC.
rows, section = [], None
for line in (RES / "full/endpoint-timeline.md").read_text().splitlines():
    if line.startswith("### "):
        section = line[4:].strip()
        continue
    m = re.match(r"\| (\d{4}-\d\d-\d\d \d\d:\d\d) \| (\d+) \| ([\d,]+) \| ([\d.]+)% \| ([\d.]+)% \|", line)
    if m and section and "flint" in section and "2026-11-09 16:00" <= m[1] <= "2026-11-10 06:00":
        rows.append(dict(bucket_start=m[1].replace(" ", "T") + ":00Z", active_trials=int(m[2]),
                         calls=int(m[3].replace(",", "")), provider_cached_pct=float(m[4]), reusable_pct=float(m[5])))
write("timeline", rows, ["results/full/endpoint-timeline.md"])

# Trial directories and original executions in one listing of the bucket.
idx = json.loads((RES / "full/index-summary.json").read_text())
rows = [dict(archive=f'Bucket listed {idx["bucket"]["listingStarted"][:16].replace("T", " ")} UTC', trial_dirs=idx["trials"],
             originals=idx["originals"], copies=idx["copies"], no_identity=idx["noIdentity"])]
write("scope", rows, ["results/full/index-summary.json"])

# Study totals: from trial directories to replays. One row.
ext = json.loads((RES / "full/assemble-summary.json").read_text())
tot, a, w = rows[-1], agg["all"]["policies"]["aff"], agg["windows"]["policies"]["aff"]
write("study", [dict(trial_dirs=tot["trial_dirs"], originals=tot["originals"], copies=tot["copies"],
                     no_identity=tot["no_identity"], extracted_trials=ext["trials"], logged_calls=ext["calls"],
                     replayable_trials=a["trials"], originals_without_successful_call=tot["originals"] - a["trials"],
                     requests=a["requests"], runs=a["units"], windows=w["units"], window_trials=w["trials"],
                     window_requests=w["requests"], routers=len(ROUTERS), replays=replays)],
      ["results/full/index-summary.json", "results/full/assemble-summary.json", "results/full/aggregate.json",
       "results/full/units.csv"])

# Slice check: runs with both a full replay and a recombined sliced replay.
rows = []
for c in json.loads((RES / "full/slice-check.json").read_text()):
    rows.append(dict(run=c["unit"], router=c["policy"], full_reuse_pct=round(100 * c["fullReuse"], 5),
                     sliced_reuse_pct=round(100 * c["slicedReuse"], 5),
                     full_prefill_m=round(c["fullPrefill"] / 1e6, 4), sliced_prefill_m=round(c["slicedPrefill"] / 1e6, 4),
                     full_sla_pct=round(100 * c["fullGoodput"], 5), sliced_sla_pct=round(100 * c["slicedGoodput"], 5),
                     full_ttft_p99_ms=round(c["fullTtftP99"], 2), sliced_ttft_p99_ms=round(c["slicedTtftP99"], 2)))
order = [r for r, _ in ROUTERS]
rows.sort(key=lambda r: (r["run"], order.index(r["router"])))
write("slices", rows, ["results/full/slice-check.json"])
