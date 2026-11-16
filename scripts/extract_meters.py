#!/usr/bin/env python3
"""Extract per-call meter logs for original, non-sealed trials in the delta archive.

This is the pilot extraction; extract_full.py covers the base archive and the
delta together. Reads the delta catalog (trials.jsonl.gz), downloads only the core shards
that hold the selected trials' agent/hlb-meter.jsonl and config.json, and writes
one gzip JSONL file per run under OUT/<run>.jsonl.gz. Each row is one trial with
its harness identity and the parsed meter calls. Run-level run.json fields go to
OUT/runs.json. Sealed-task trials are never opened; result.json and trajectories
are not read.

Locations: HLB_ARCHIVE_BUCKET (required), HLB_DELTA_PREFIX (default "delta/"),
STAGE (scratch directory, default "stage").
"""
import argparse, gzip, json, os, tarfile, tempfile, time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import zstandard
from google.cloud import storage

BUCKET = os.environ.get("HLB_ARCHIVE_BUCKET", "")
PREFIX = os.environ.get("HLB_DELTA_PREFIX", "delta/")
STAGE = os.environ.get("STAGE", "stage")
CALL_KEYS = ("ts", "status", "ttfb_s", "latency_s", "input", "cached", "output", "reasoning",
             "req_bytes", "resp_bytes", "model", "path", "stream", "effort_sent")
RUN_KEYS = ("run_id", "model", "provider", "stage", "reasoning_effort", "harnesses", "harness_versions",
            "n_trials", "n_new", "n_reused", "max_concurrent_trials", "created_at", "updated_at", "state")
WANT = {}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def parse_meter(data):
    calls, events = [], []
    for line in data.splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("method") == "POST" and "input" in r:
            calls.append({k: r[k] for k in CALL_KEYS if k in r})
        elif "event" in r:
            events.append(r)
    calls.sort(key=lambda c: c["ts"])
    return calls, events


def init(want):
    global WANT
    WANT = want


def read_shard(key):
    """Return {trial: {meter calls, events, config fields}} and {run: run.json fields} for one shard."""
    trials, runs = defaultdict(dict), {}
    blob = storage.Client().bucket(BUCKET).blob(PREFIX + key)
    with tempfile.TemporaryFile(dir=STAGE) as tmp:
        blob.download_to_file(tmp); tmp.seek(0)
        with zstandard.ZstdDecompressor().stream_reader(tmp) as stream, tarfile.open(fileobj=stream, mode="r|") as tar:
            for m in tar:
                if not m.isfile():
                    continue
                path = m.name.removeprefix("raw/")
                parts = path.split("/")
                if len(parts) == 3 and parts[0] == "runs" and parts[2] == "run.json":
                    d = json.loads(tar.extractfile(m).read())
                    runs[parts[1]] = {k: d.get(k) for k in RUN_KEYS if k in d}
                    continue
                if len(parts) < 5:
                    continue
                trial, rel = "/".join(parts[:4]), "/".join(parts[4:])
                if trial not in WANT or rel not in ("agent/hlb-meter.jsonl", "config.json"):
                    continue
                data = tar.extractfile(m).read()
                if rel == "config.json":
                    d = json.loads(data)
                    trials[trial]["configAgentKwargs"] = {k: v for k, v in ((d.get("agent") or {}).get("kwargs") or {}).items()
                                                          if k in ("version", "model_api")}
                else:
                    trials[trial]["calls"], trials[trial]["events"] = parse_meter(data)
    return dict(trials), runs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="delta/catalog/trials.jsonl.gz")
    ap.add_argument("--out", default="meters")
    ap.add_argument("--runs", nargs="*", help="limit to these runs")
    ap.add_argument("--workers", type=int, default=32)
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    if not BUCKET:
        raise SystemExit("set HLB_ARCHIVE_BUCKET")
    os.makedirs(STAGE, exist_ok=True)

    want, shards = {}, set()
    for line in gzip.open(a.catalog, "rt"):
        r = json.loads(line)
        if r.get("sealedTask") or not r.get("originalExecution") or "meter" not in r.get("members", {}):
            continue
        if a.runs and r["run"] not in a.runs:
            continue
        want[r["trial"]] = {k: r.get(k) for k in ("run", "benchmark", "taskKey", "harness", "harnessVersion",
                                                    "modelName", "effort", "atifHarness", "steps")}
        for kind in ("meter", "config"):
            if kind in r["members"]:
                shards.add(r["members"][kind]["shard"])
    log(f"{len(want)} trials in {len(shards)} shards")

    found, runs = {}, {}
    with ProcessPoolExecutor(min(a.workers, len(shards)), initializer=init, initargs=(want,)) as pool:
        for i, (tr, rn) in enumerate(pool.map(read_shard, sorted(shards))):
            for k, v in tr.items():
                found.setdefault(k, {}).update(v)
            runs.update(rn)
            if (i + 1) % 25 == 0:
                log(f"{i + 1}/{len(shards)} shards")

    by_run = defaultdict(list)
    missing = 0
    for trial, meta in want.items():
        got = found.get(trial, {})
        if "calls" not in got:
            missing += 1
            continue
        by_run[meta["run"]].append({"trial": trial, **meta, **got})
    for run, rows in by_run.items():
        rows.sort(key=lambda r: (r["calls"][0]["ts"] if r["calls"] else 0, r["trial"]))
        with gzip.open(out / f"{run}.jsonl.gz", "wt") as f:
            for r in rows:
                f.write(json.dumps(r, separators=(",", ":")) + "\n")
    (out / "runs.json").write_text(json.dumps(runs, indent=1, sort_keys=True))
    log(f"wrote {sum(map(len, by_run.values()))} trials across {len(by_run)} runs; {missing} without meter")


if __name__ == "__main__":
    main()
