#!/usr/bin/env python3
"""Download the meter log and config of each original trial that a previous pass did not have.

Usage: fetch_meters.py INDEX_DIR LISTING_DIR OUT
INDEX_DIR holds index_bucket.py's fetch.json; LISTING_DIR the per-run listings (for sizes and Xet hashes,
so files come straight from Xet storage). Writes OUT/new-trials.jsonl.gz, one row per trial in
extract_full.py's meter-file shape (calls, events, config fields), and OUT/new-runs.json from run.json.
Downloaded files land in OUT/raw and are parsed as data only.
"""
import gzip, json, re, sys, time
from pathlib import Path
from huggingface_hub import BucketFile, download_bucket_files

BUCKET = "joelniklaus/harness-leaderboard"
CALL_KEYS = ("ts", "status", "ttfb_s", "latency_s", "input", "cached", "output", "reasoning",
             "req_bytes", "resp_bytes", "model", "path", "stream", "effort_sent")
RUN_KEYS = ("run_id", "model", "provider", "stage", "reasoning_effort", "harnesses", "harness_versions",
            "n_trials", "n_new", "n_reused", "max_concurrent_trials", "created_at", "updated_at", "state")
ADAPTERS = {"HFClaudeCode": "claude-code", "HFClaudeCodeBare": "claude-code-bare", "HFCodex": "codex",
            "HFDeepSeekHarness": "deepseek-harness", "HFFx": "fx", "HFGrokBuild": "grok-build", "HFHermes": "hermes",
            "HFKimiCode": "kimi-code", "HFMiniSweAgent": "mini-swe-agent", "HFOhMyPi": "oh-my-pi",
            "HFOpenClaw": "openclaw", "HFOpenCode": "opencode", "HFPi": "pi", "HFQwenCode": "qwen-code"}

idx, listing, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
raw = out / "raw"
raw.mkdir(parents=True, exist_ok=True)
fetch = json.loads((idx / "fetch.json").read_text())
runs = sorted({t.split("/")[1] for t in fetch})
want = {f"{t}/{rel}" for t in fetch for rel in ("agent/hlb-meter.jsonl", "config.json")} | {f"runs/{r}/run.json" for r in runs}
files = {}
for r in runs:
    for line in gzip.open(listing / f"{r}.jsonl.gz", "rt"):
        o = json.loads(line)
        if o["path"] in want:
            files[o["path"]] = o
print(len(fetch), "trials,", len(files), "files to fetch", flush=True)


def local(p):
    return raw / p


todo = [o for o in files.values() if not (local(o["path"]).exists() and local(o["path"]).stat().st_size == o["size"])]
for i in range(0, len(todo), 2000):
    batch = todo[i:i + 2000]
    pairs = []
    for o in batch:
        local(o["path"]).parent.mkdir(parents=True, exist_ok=True)
        pairs.append((BucketFile(type="file", path=o["path"], size=o["size"], xetHash=o["xetHash"]), local(o["path"])))
    for attempt in range(6):
        try:
            download_bucket_files(BUCKET, pairs, raise_on_missing_files=False, token=False)
            break
        except Exception as e:
            print("RETRY", type(e).__name__, str(e)[:160], flush=True)
            time.sleep(min(300, 20 * 2 ** attempt))
    print(time.strftime("%H:%M:%S"), f"{min(i + 2000, len(todo))}/{len(todo)} files", flush=True)


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


missing = 0
with gzip.open(out / "new-trials.jsonl.gz", "wt") as f:
    for t in fetch:
        m, c = local(f"{t}/agent/hlb-meter.jsonl"), local(f"{t}/config.json")
        if not m.exists():
            missing += 1
            continue
        row = {"trial": t}
        try:
            row["calls"], row["events"] = parse_meter(m.read_bytes())
        except ValueError:
            row["parseErrors"] = ["agent/hlb-meter.jsonl"]
        if c.exists():
            try:
                row.update(config_fields(json.loads(c.read_bytes())))
            except ValueError:
                row.setdefault("parseErrors", []).append("config.json")
        f.write(json.dumps(row, separators=(",", ":")) + "\n")
runinfo = {}
for r in runs:
    p = local(f"runs/{r}/run.json")
    if p.exists():
        try:
            d = json.loads(p.read_bytes())
            runinfo[r] = {k: d.get(k) for k in RUN_KEYS if k in d}
        except ValueError:
            pass
(out / "new-runs.json").write_text(json.dumps(runinfo, indent=1, sort_keys=True))
print(json.dumps(dict(trials=len(fetch), missingMeter=missing, runs=len(runinfo))), flush=True)
