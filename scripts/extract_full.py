#!/usr/bin/env python3
"""Per-call meter logs for every original Harness Leaderboard trial in the base archive and the delta.

The base archive is the first snapshot of the public bucket; the delta holds the
objects published after it (delta_ingest.py, catalog.py).

`index` builds one row per trial directory from the base archive's frozen
manifest and the delta catalog, and marks original executions. A trial's
identity is the Xet hash of its meter log, or of its ATIF trajectory when the
meter log is missing or under 256 bytes. Within the base archive, the first
trial (by run ID, then trial path) that holds an identity is the original. Delta
originals come from its catalog, which applies the same rule after excluding
base identities. Trials on sealed tasks (ref/sealed-tasks.json, tasks a separate
analysis had kept unopened) are included and flagged.

`extract` scans the archive shards once, keeps agent/hlb-meter.jsonl and
config.json for original trials, and writes OUT/meters/<run>.jsonl.gz with one
row per trial (both archives merged per run). Each shard's result is cached under
OUT/cache, so an interrupted scan resumes. result.json and trajectories are not
read.

Locations come from the environment:
  HLB_ARCHIVE_BUCKET  Cloud Storage bucket that holds the mirror (required for `extract`)
  HLB_BASE_PREFIX     object prefix of the base archive (default "base/")
  HLB_DELTA_PREFIX    object prefix of the delta archive (default "delta/")
  HLB_DELTA_ROOT      delta_ingest.py's working directory, with catalog/ and ref/ (default "delta")
  FULL_ROOT           output directory (default "full"); `index` expects the base archive's
                      source-manifest.tar.zst there as base-source-manifest.tar.zst
"""
import argparse, gzip, json, os, re, tarfile, tempfile, time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import zstandard
from google.cloud import storage

BUCKET = os.environ.get("HLB_ARCHIVE_BUCKET", "")
BASE = os.environ.get("HLB_BASE_PREFIX", "base/")
DELTA = os.environ.get("HLB_DELTA_PREFIX", "delta/")
OUT = Path(os.environ.get("FULL_ROOT", "full"))
DELTA_ROOT = Path(os.environ.get("HLB_DELTA_ROOT", "delta"))
MIN_IDENTITY_BYTES = 256
CALL_KEYS = ("ts", "status", "ttfb_s", "latency_s", "input", "cached", "output", "reasoning",
             "req_bytes", "resp_bytes", "model", "path", "stream", "effort_sent")
RUN_KEYS = ("run_id", "model", "provider", "stage", "reasoning_effort", "harnesses", "harness_versions",
            "n_trials", "n_new", "n_reused", "max_concurrent_trials", "created_at", "updated_at", "state")
ADAPTERS = {"HFClaudeCode": "claude-code", "HFClaudeCodeBare": "claude-code-bare", "HFCodex": "codex",
            "HFDeepSeekHarness": "deepseek-harness", "HFFx": "fx", "HFGrokBuild": "grok-build", "HFHermes": "hermes",
            "HFKimiCode": "kimi-code", "HFMiniSweAgent": "mini-swe-agent", "HFOhMyPi": "oh-my-pi",
            "HFOpenClaw": "openclaw", "HFOpenCode": "opencode", "HFPi": "pi", "HFQwenCode": "qwen-code"}
KINDS = {"agent/hlb-meter.jsonl": "meter", "agent/trajectory.json": "trajectory", "config.json": "config"}
WANT = {}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def split(path):
    s = path.split("/")
    if len(s) >= 5 and s[0] == "runs":
        return s[1], "/".join(s[:4]), s[2], s[3], "/".join(s[4:])
    return None


def harness_of(adapter):
    if not adapter:
        return None
    return ADAPTERS.get(adapter) or re.sub(r"(?<!^)(?=[A-Z])", "-", adapter.removeprefix("HF")).lower()


def config_fields(d):
    agent = d.get("agent") or {}
    kwargs = agent.get("kwargs") or {}
    adapter = (agent.get("import_path") or "").rsplit(":", 1)[-1] or None
    return dict(adapter=adapter, harness=harness_of(adapter), harnessVersion=kwargs.get("version"),
                modelName=agent.get("model_name"), effort=((d.get("environment") or {}).get("kwargs") or {}).get("reasoning_effort"))


def identity(members):
    for kind in ("meter", "trajectory"):
        m = members.get(kind)
        if m and m["size"] >= MIN_IDENTITY_BYTES and m.get("xet"):
            return kind, m["xet"]
    return None, None


def build_index():
    sealed = set(json.loads((DELTA_ROOT / "ref/sealed-tasks.json").read_text())["tasks"])
    trials = defaultdict(lambda: dict(members={}))
    with open(OUT / "base-source-manifest.tar.zst", "rb") as f, \
            zstandard.ZstdDecompressor().stream_reader(f) as s, tarfile.open(fileobj=s, mode="r|") as tar:
        for m in tar:
            if not (m.isfile() and m.name.endswith(".jsonl")):
                continue
            for line in tar.extractfile(m):
                r = json.loads(line)
                sp = split(r["path"])
                if not sp or sp[4] not in KINDS:
                    continue
                run, trial, bench, tdir, rel = sp
                t = trials[trial]
                t.update(run=run, benchmark=bench, taskKey=tdir.rsplit("__", 1)[0])
                t["members"][KINDS[rel]] = dict(size=r["size"], xet=r.get("xetHash"))
    rows, first = [], {}
    for name, t in sorted(trials.items(), key=lambda kv: (kv[1]["run"], kv[0])):
        kind, ident = identity(t["members"])
        dup = first.get(ident) if ident else None
        if ident and ident not in first:
            first[ident] = name
        rows.append(dict(trial=name, source="base", run=t["run"], benchmark=t["benchmark"], taskKey=t["taskKey"],
                         sealedTask=t["taskKey"] in sealed, identityKind=kind, identity=ident, duplicateOf=dup,
                         originalExecution=bool(ident) and dup is None, hasMeter="meter" in t["members"],
                         meterBytes=(t["members"].get("meter") or {}).get("size")))
    for line in gzip.open(DELTA_ROOT / "catalog/trials.jsonl.gz", "rt"):
        r = json.loads(line)
        meter = r["members"].get("meter") or {}
        rows.append(dict(trial=r["trial"], source="delta", run=r["run"], benchmark=r["benchmark"], taskKey=r["taskKey"],
                         sealedTask=r["sealedTask"], identityKind=(r.get("identity") or {}).get("kind"),
                         identity=(r.get("identity") or {}).get("xetHash"),
                         duplicateOf=r.get("duplicateOf") or ("base" if r.get("copiedFromBase") else None),
                         originalExecution=r["originalExecution"], hasMeter=bool(meter), meterBytes=meter.get("bytes"),
                         shards=sorted({(r["members"].get(k) or {}).get("shard") for k in ("meter", "config")} - {None})))
    with gzip.open(OUT / "index.jsonl.gz", "wt") as f:
        for r in rows:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")
    summary = defaultdict(Counter)
    for r in rows:
        c = summary[r["source"]]
        c["trials"] += 1; c["original"] += r["originalExecution"]; c["sealed"] += r["sealedTask"]
        c["originalWithMeter"] += r["originalExecution"] and r["hasMeter"]
        c["originalSealedWithMeter"] += r["originalExecution"] and r["hasMeter"] and r["sealedTask"]
        c["withoutIdentity"] += r["identity"] is None
        c["runs:" + r["run"]] = 1
    out = {k: {kk: vv for kk, vv in v.items() if not kk.startswith("runs:")} | {"runs": sum(1 for kk in v if kk.startswith("runs:"))}
           for k, v in summary.items()}
    out["runsInBoth"] = len({r["run"] for r in rows if r["source"] == "base"} & {r["run"] for r in rows if r["source"] == "delta"})
    (OUT / "index-summary.json").write_text(json.dumps(out, indent=1))
    log(json.dumps(out))


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


def read_shard(job):
    prefix, key = job
    tag = "base" if prefix == BASE else "delta"
    cache = OUT / "cache" / f"{tag}-{key.rsplit('/', 1)[-1]}.json.gz"
    if cache.exists():
        return json.loads(gzip.decompress(cache.read_bytes()))
    trials, runs = defaultdict(dict), {}
    with tempfile.TemporaryFile(dir=OUT / "stage") as tmp:
        for attempt in range(5):
            try:
                tmp.seek(0); tmp.truncate()
                storage.Client().bucket(BUCKET).blob(prefix + key).download_to_file(tmp)
                break
            except Exception as e:  # transient storage errors
                if attempt == 4:
                    raise
                time.sleep(10 * (attempt + 1))
        tmp.seek(0)
        with zstandard.ZstdDecompressor().stream_reader(tmp) as stream, tarfile.open(fileobj=stream, mode="r|") as tar:
            for m in tar:
                if not m.isfile():
                    continue
                path = m.name.removeprefix("raw/")
                parts = path.split("/")
                if len(parts) == 3 and parts[0] == "runs" and parts[2] == "run.json":
                    try:
                        d = json.loads(tar.extractfile(m).read())
                        runs[parts[1]] = {k: d.get(k) for k in RUN_KEYS if k in d}
                    except ValueError:
                        pass
                    continue
                if len(parts) < 5:
                    continue
                trial, rel = "/".join(parts[:4]), "/".join(parts[4:])
                if rel not in ("agent/hlb-meter.jsonl", "config.json") or trial not in WANT:
                    continue
                data = tar.extractfile(m).read()
                try:
                    if rel == "config.json":
                        trials[trial].update(config_fields(json.loads(data)))
                    else:
                        trials[trial]["calls"], trials[trial]["events"] = parse_meter(data)
                except ValueError:
                    trials[trial].setdefault("parseErrors", []).append(rel)
    value = [dict(trials), runs]
    tmp_path = cache.with_suffix(".tmp")
    tmp_path.write_bytes(gzip.compress(json.dumps(value).encode()))
    os.replace(tmp_path, cache)
    return value


def extract(workers):
    (OUT / "cache").mkdir(exist_ok=True); (OUT / "stage").mkdir(exist_ok=True); (OUT / "meters").mkdir(exist_ok=True)
    want, jobs = {}, set()
    for line in gzip.open(OUT / "index.jsonl.gz", "rt"):
        r = json.loads(line)
        if r["originalExecution"] and r["hasMeter"]:
            want[r["trial"]] = {k: r[k] for k in ("source", "run", "benchmark", "taskKey", "sealedTask")}
            for s in r.get("shards") or []:
                jobs.add((DELTA, s))
    ledger = json.loads((DELTA_ROOT / "ref/base-archive-ledger.json").read_text())
    jobs |= {(BASE, s["archiveKey"]) for s in ledger}
    jobs = sorted(jobs, key=lambda j: (j[0] != BASE, j[1]))
    log(f"{len(want)} original trials with meter logs; {len(jobs)} shards to scan")
    found, runs = {}, {}
    with ProcessPoolExecutor(workers, initializer=init, initargs=(want,)) as pool:
        for i, (tr, rn) in enumerate(pool.map(read_shard, jobs, chunksize=4)):
            for k, v in tr.items():
                found.setdefault(k, {}).update(v)
            runs.update(rn)
            if (i + 1) % 100 == 0:
                log(f"{i + 1}/{len(jobs)} shards, {sum('calls' in v for v in found.values())} meter logs")
    by_run, missing = defaultdict(list), Counter()
    for trial, meta in want.items():
        got = found.get(trial, {})
        if "calls" not in got:
            missing[meta["source"]] += 1
            continue
        by_run[meta["run"]].append({"trial": trial, **meta, **got})
    for run, rows in by_run.items():
        rows.sort(key=lambda r: (r["calls"][0]["ts"] if r["calls"] else 0, r["trial"]))
        with gzip.open(OUT / "meters" / f"{run}.jsonl.gz", "wt") as f:
            for r in rows:
                f.write(json.dumps(r, separators=(",", ":")) + "\n")
    (OUT / "meters" / "runs.json").write_text(json.dumps(runs, indent=1, sort_keys=True))
    n = sum(map(len, by_run.values()))
    calls = sum(len(r["calls"]) for rows in by_run.values() for r in rows)
    summary = dict(trials=n, calls=calls, runs=len(by_run), missingMeter=dict(missing),
                   bySource=dict(Counter(r["source"] for rows in by_run.values() for r in rows)),
                   sealedTrials=sum(r["sealedTask"] for rows in by_run.values() for r in rows))
    (OUT / "meters" / "extract-summary.json").write_text(json.dumps(summary, indent=1))
    log(json.dumps(summary))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("index", "extract"))
    ap.add_argument("--workers", type=int, default=40)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.step == "extract" and not BUCKET:
        raise SystemExit("set HLB_ARCHIVE_BUCKET")
    build_index() if a.step == "index" else extract(a.workers)


if __name__ == "__main__":
    main()
