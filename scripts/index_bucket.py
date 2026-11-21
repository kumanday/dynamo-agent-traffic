#!/usr/bin/env python3
"""Mark original executions in a bucket listing and compare them with a previous pass.

Same rule as extract_full.py: a trial's identity is the Xet hash of agent/hlb-meter.jsonl, or of
agent/trajectory.json when the meter log is missing or under 256 bytes; the first trial by
(run ID, trial path) holding an identity is the original. Here the rule runs over one listing of the
whole public bucket, so originals that sat in runs now private move to the first public copy, and
restored older runs take back the trials they ran first. Per run, runs-diff.json says whether its\noriginals are unchanged, changed, new or removed against the previous pass.

Usage: index_bucket.py LISTING_DIR OLD_INDEX OUT_DIR
OLD_INDEX is a previous pass's index.jsonl.gz, or - for none (every original is then fetched).
Writes OUT/index.jsonl.gz (one row per trial), OUT/runs-diff.json (per run: status and counts),
OUT/fetch.json (trial paths whose meter log and config must be downloaded) and OUT/summary.json.
"""
import gzip, json, sys
from collections import Counter, defaultdict
from pathlib import Path

MIN = 256
KINDS = {"agent/hlb-meter.jsonl": "meter", "agent/trajectory.json": "trajectory", "config.json": "config"}
listing, old_index, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
out.mkdir(parents=True, exist_ok=True)
bucket = json.loads((listing / "bucket.json").read_text())

trials = defaultdict(dict)
for run in bucket["runs"]:
    p = listing / f"{run}.jsonl.gz"
    if not p.exists():
        sys.exit(f"run not listed yet: {run}")
    for line in gzip.open(p, "rt"):
        r = json.loads(line)
        s = r["path"].split("/")
        if len(s) >= 5 and s[0] == "runs":
            rel = "/".join(s[4:])
            if rel in KINDS:
                trials["/".join(s[:4])][KINDS[rel]] = dict(size=r["size"], xet=r["xetHash"])

old, old_orig_by_run, sealed_keys = {}, defaultdict(set), set()
for line in (gzip.open(old_index, "rt") if str(old_index) != "-" else []):
    r = json.loads(line)
    old[r["trial"]] = r
    if r["originalExecution"]:
        old_orig_by_run[r["run"]].add(r["identity"])
    if r["sealedTask"]:
        sealed_keys.add((r["benchmark"], r["taskKey"]))
old_identities = {r["identity"] for r in old.values() if r["originalExecution"]}

rows, first = [], {}
for name in sorted(trials, key=lambda t: (t.split("/")[1], t)):
    m = trials[name]
    _, run, bench, tdir = name.split("/")
    ident = kind = None
    for k in ("meter", "trajectory"):
        x = m.get(k)
        if x and x["size"] >= MIN and x.get("xet"):
            ident, kind = x["xet"], k
            break
    dup = first.get(ident) if ident else None
    if ident and dup is None:
        first[ident] = name
    task = tdir.rsplit("__", 1)[0]
    rows.append(dict(trial=name, run=run, benchmark=bench, taskKey=task, sealedTask=(bench, task) in sealed_keys,
                     identityKind=kind, identity=ident, duplicateOf=dup, originalExecution=bool(ident) and dup is None,
                     hasMeter="meter" in m, meterBytes=(m.get("meter") or {}).get("size"),
                     inOldOriginals=ident in old_identities))

with gzip.open(out / "index.jsonl.gz", "wt") as f:
    for r in rows:
        f.write(json.dumps(r, separators=(",", ":")) + "\n")

new_orig_by_run = defaultdict(set)
for r in rows:
    if r["originalExecution"] and r["hasMeter"]:
        new_orig_by_run[r["run"]].add(r["identity"])
diff = {}
for run in sorted(set(new_orig_by_run) | set(old_orig_by_run)):
    a, b = old_orig_by_run.get(run, set()), new_orig_by_run.get(run, set())
    status = ("unchanged" if a == b else "removed" if not b else "new" if not a else "changed")
    diff[run] = dict(status=status, old=len(a), new=len(b), added=len(b - a), dropped=len(a - b))
(out / "runs-diff.json").write_text(json.dumps(diff, indent=1))
fetch = sorted(r["trial"] for r in rows if r["originalExecution"] and r["hasMeter"] and not r["inOldOriginals"])
(out / "fetch.json").write_text(json.dumps(fetch))
c = Counter(v["status"] for v in diff.values())
summary = dict(bucket={k: bucket.get(k) for k in ("listingStarted", "listingFinished", "before", "after")},
               trials=len(rows), originals=sum(r["originalExecution"] for r in rows),
               originalsWithMeter=sum(r["originalExecution"] and r["hasMeter"] for r in rows),
               copies=sum(r["duplicateOf"] is not None for r in rows), noIdentity=sum(r["identity"] is None for r in rows),
               runsWithOriginals=len(new_orig_by_run), runStatus=dict(c), toFetch=len(fetch),
               reusedFromOld=sum(r["originalExecution"] and r["hasMeter"] and r["inOldOriginals"] for r in rows))
(out / "summary.json").write_text(json.dumps(summary, indent=1))
print(json.dumps(summary, indent=1))
