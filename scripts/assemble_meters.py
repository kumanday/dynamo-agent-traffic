#!/usr/bin/env python3
"""Build per-run meter files from a previous pass (optional) plus the fetched trials.

Usage: assemble_meters.py OLD_ROOT NEW_ROOT INDEX_DIR FETCH_DIR   (OLD_ROOT - for none)
OLD_ROOT is a previous pass's root (index.jsonl.gz, meters/). Each original trial in today's
index takes its calls from the old meter row with the same identity (the content is identical by hash)
or from the fetched row. Writes NEW_ROOT/meters/<run>.jsonl.gz, meters/runs.json and assemble-summary.json.
"""
import gzip, json, sys
from collections import Counter, defaultdict
from pathlib import Path

old, new, idx, fetched = (Path(a) for a in sys.argv[1:5])
(new / "meters").mkdir(parents=True, exist_ok=True)
old_ident = {}
for line in (gzip.open(old / "index.jsonl.gz", "rt") if str(old) != "-" else []):
    r = json.loads(line)
    if r["originalExecution"]:
        old_ident[r["trial"]] = r["identity"]
content = {}
KEEP = ("calls", "events", "adapter", "harness", "harnessVersion", "modelName", "effort", "parseErrors")
for p in (sorted((old / "meters").glob("*.jsonl.gz")) if str(old) != "-" else []):
    for line in gzip.open(p, "rt"):
        r = json.loads(line)
        i = old_ident.get(r["trial"])
        if i:
            content[i] = {k: r[k] for k in KEEP if k in r}
by_trial = {}
for line in gzip.open(fetched / "new-trials.jsonl.gz", "rt"):
    r = json.loads(line)
    by_trial[r["trial"]] = {k: r[k] for k in KEEP if k in r}
rows, src, lacking = defaultdict(list), Counter(), 0
for line in gzip.open(idx / "index.jsonl.gz", "rt"):
    r = json.loads(line)
    if not (r["originalExecution"] and r["hasMeter"]):
        continue
    c = content.get(r["identity"]) if r["inOldOriginals"] else by_trial.get(r["trial"])
    if c is None or "calls" not in c:
        lacking += 1
        continue
    src["previous" if r["inOldOriginals"] else "fetched"] += 1
    rows[r["run"]].append({"trial": r["trial"], "source": "previous" if r["inOldOriginals"] else "fetched",
                           "run": r["run"], "benchmark": r["benchmark"], "taskKey": r["taskKey"],
                           "sealedTask": r["sealedTask"], **c})
for run, rs in rows.items():
    rs.sort(key=lambda r: (r["calls"][0]["ts"] if r["calls"] else 0, r["trial"]))
    with gzip.open(new / "meters" / f"{run}.jsonl.gz", "wt") as f:
        for r in rs:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")
runinfo = json.loads((old / "meters" / "runs.json").read_text()) if str(old) != "-" else {}
runinfo.update(json.loads((fetched / "new-runs.json").read_text()))
(new / "meters" / "runs.json").write_text(json.dumps({k: v for k, v in runinfo.items() if k in rows}, indent=1, sort_keys=True))
calls = sum(len(r["calls"]) for rs in rows.values() for r in rs)
summary = dict(runs=len(rows), trials=sum(map(len, rows.values())), calls=calls, bySource=dict(src),
               lackingContent=lacking, sealedTrials=sum(r["sealedTask"] for rs in rows.values() for r in rs))
(new / "assemble-summary.json").write_text(json.dumps(summary, indent=1))
print(json.dumps(summary))
