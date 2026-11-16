"""Catalog everything the delta adds to the Harness Leaderboard archive.

Run from delta_ingest.py's working directory after the core phase completes, and again after the archive
phase. It reads the delta manifest, the shard acknowledgements, the delta core shards and, for the
baseline, the base archive's core shards in Cloud Storage (HLB_BASE_PREFIX, default "base/"). Parsed
shards are cached in ./catalog/cache/. ./ref/ holds base-archive-ledger.json (the base archive's shard
ledger) and sealed-tasks.json.

Outputs in ./catalog/ (also uploaded under the delta prefix, in catalog/):
  members.jsonl.gz  every delta object: path, size, xetHash, SHA-256, run, trial, phase, shard key
  trials.jsonl.gz   one row per trial directory: lane flags, members present, harness and version from the
                    trial config, model, ATIF and meter summaries, copy and duplicate flags
  runs.json         one row per run prefix with run.json fields and delta counts
  summary.json      totals, verification, harness@version counts against the base archive
  CATALOG.md        readable summary

Harness identity comes from each trial's config.json adapter class and version. ATIF agent names are kept
as atifHarness; some harnesses report another name there (Oh My Pi reports "pi").

A trial is a copy when its meter log (or, without one, its ATIF file) has the same Xet hash as an object in
the base archive or in an earlier delta run. Copies come from reused trials and did not execute in the run that
lists them; originalExecution marks the rest.

Sealed tasks (ref/sealed-tasks.json, tasks a separate analysis kept unopened) keep path, size, shard, Xet
hash and receipt digest only. Their trial contents stay unparsed, in the base archive and the delta alike.
ref/discovery*.jsonl.gz, when present, lists trajectory digests that analysis had already indexed; it only
sets a flag on matching trials.
"""
import gzip, hashlib, json, os, re, tarfile, tempfile, time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import zstandard
from google.cloud import storage
import delta_ingest as D

ROOT = D.ROOT
REF = ROOT / "ref"
OUT = ROOT / "catalog"
CACHE = OUT / "cache"
BASE_PREFIX = os.environ.get("HLB_BASE_PREFIX", "base/")
SEALED = set()
TRIAL_FILES = {"agent/trajectory.json": "trajectory", "agent/hlb-meter.jsonl": "meter", "result.json": "result",
               "config.json": "config", "lock.json": "lock"}
ADAPTERS = {"HFClaudeCode": "claude-code", "HFClaudeCodeBare": "claude-code-bare", "HFCodex": "codex",
            "HFDeepSeekHarness": "deepseek-harness", "HFFx": "fx", "HFGrokBuild": "grok-build", "HFHermes": "hermes",
            "HFKimiCode": "kimi-code", "HFMiniSweAgent": "mini-swe-agent", "HFOhMyPi": "oh-my-pi",
            "HFOpenClaw": "openclaw", "HFOpenCode": "opencode", "HFPi": "pi", "HFQwenCode": "qwen-code"}
MIN_IDENTITY_BYTES = 256


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def split(p):
    s = p.split("/")
    if s[0] != "runs" or len(s) < 3:
        return None, None, None, None, p
    if len(s) >= 5:
        return s[1], "/".join(s[:4]), s[2], s[3], "/".join(s[4:])
    return s[1], None, None, None, "/".join(s[2:])


def task_of(trial_dir):
    return trial_dir.rsplit("__", 1)[0]


def harness_of(adapter):
    if not adapter:
        return None
    if adapter in ADAPTERS:
        return ADAPTERS[adapter]
    return re.sub(r"(?<!^)(?=[A-Z])", "-", adapter.removeprefix("HF")).lower()


def reconstruct(receipt):
    """Replay delta_ingest's deterministic batching so every path maps to its shard."""
    where, batches, serial = {}, [], 0
    for phase in ("core", "archive"):
        for batch in D.groups(receipt, phase == "core"):
            digest = hashlib.sha256(b"".join(D.encoded(x) for x in batch)).hexdigest()
            batches.append((serial, phase, len(batch), digest))
            for row in batch:
                where[row["path"]] = (serial, phase, row["size"], row["xetHash"])
            serial += 1
    return where, batches


def verify(batches):
    acks = {int(p.stem): json.loads(p.read_text()) for p in (ROOT / "ack").glob("*.json")}
    status, problems = Counter(), []
    for serial, phase, n, digest in batches:
        a = acks.get(serial)
        if a is None:
            status[f"{phase}Pending"] += 1
        elif a["manifestDigest"] != digest or a["objects"] != n or a["phase"] != phase:
            status["mismatch"] += 1; problems.append(serial)
        else:
            status[f"{phase}Acked"] += 1
            status["unavailableObjects"] += a["unavailable"]
    return acks, dict(status), problems


def run_fields(d):
    keep = ("run_id", "model", "provider", "stage", "reasoning_effort", "harnesses", "harness_versions", "n_trials",
            "n_new", "n_reused", "max_concurrent_trials", "n_attempts", "created_at", "updated_at", "state")
    return {k: d.get(k) for k in keep if k in d}


def config_fields(d):
    agent = d.get("agent") or {}
    kwargs = agent.get("kwargs") or {}
    adapter = (agent.get("import_path") or "").rsplit(":", 1)[-1] or None
    return dict(task=(d.get("task") or {}).get("path", "").removeprefix("tasks/") or None,
                adapter=adapter, harness=harness_of(adapter), harnessVersion=kwargs.get("version"),
                modelName=agent.get("model_name"), modelApi=kwargs.get("model_api"),
                effort=((d.get("environment") or {}).get("kwargs") or {}).get("reasoning_effort"))


def atif_fields(d):
    agent = d.get("agent") or {}
    fm = d.get("final_metrics") or {}
    return dict(atifSchema=d.get("schema_version"), atifHarness=agent.get("name"), atifHarnessVersion=agent.get("version"),
                atifModel=agent.get("model_name"), steps=len(d.get("steps") or []),
                atifPromptTokens=fm.get("total_prompt_tokens"), atifCachedTokens=fm.get("total_cached_tokens"))


def meter_fields(data):
    calls = inp = cached = out = 0
    first = last = None
    for line in data.splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("method") != "POST" or "input" not in r:
            continue
        calls += 1
        inp += int(r.get("input") or 0); cached += int(r.get("cached") or 0); out += int(r.get("output") or 0)
        ts = float(r["ts"]); first = ts if first is None else min(first, ts); last = ts if last is None else max(last, ts)
    return dict(meterCalls=calls, meterInput=inp, meterCached=cached, meterOutput=out,
                meterFirstTs=first, meterLastTs=last)


def init_reader(sealed):
    global SEALED
    SEALED = set(sealed)


def read_core(job):
    """Parse one core shard. mode 'delta' parses config, ATIF and meter; 'base' parses config and run.json."""
    mode, prefix, key = job
    cached = CACHE / f"{mode}-{key.rsplit('/', 1)[-1]}.json"
    if cached.exists():
        return json.loads(cached.read_text())
    blob = storage.Client().bucket(D.GCS_BUCKET).blob(prefix + key)
    receipts, runs, trials = {}, {}, defaultdict(dict)
    with tempfile.TemporaryFile(dir=ROOT / "stage") as tmp:
        blob.download_to_file(tmp); tmp.seek(0)
        with zstandard.ZstdDecompressor().stream_reader(tmp) as stream, tarfile.open(fileobj=stream, mode="r|") as tar:
            for m in tar:
                if not m.isfile():
                    continue
                name = m.name
                if name == D.RECEIPTS:
                    if mode == "delta":
                        for line in tar.extractfile(m).read().splitlines():
                            r = json.loads(line)
                            receipts[r["path"]] = r.get("sha256")
                    continue
                run, trial, bench, tdir, rel = split(name.removeprefix("raw/"))
                if trial is None:
                    if run and rel == "run.json":
                        runs[run] = run_fields(json.loads(tar.extractfile(m).read()))
                    continue
                if task_of(tdir) in SEALED:
                    continue
                if mode == "base" and rel != "config.json":
                    continue
                try:
                    if rel == "config.json":
                        trials[trial].update(config_fields(json.loads(tar.extractfile(m).read())))
                    elif rel == "agent/trajectory.json":
                        trials[trial].update(atif_fields(json.loads(tar.extractfile(m).read())))
                    elif rel == "agent/hlb-meter.jsonl":
                        trials[trial].update(meter_fields(tar.extractfile(m).read()))
                except Exception:
                    trials[trial].setdefault("parseErrors", []).append(rel)
    value = [receipts, runs, dict(trials)]
    tmp_path = cached.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(value))
    os.replace(tmp_path, cached)
    return value


def parse_shards(jobs, sealed):
    receipts, runs, trials = {}, {}, {}
    with ProcessPoolExecutor(min(40, os.cpu_count()), initializer=init_reader, initargs=(sealed,)) as pool:
        for rc, rn, tr in pool.map(read_core, jobs, chunksize=2):
            receipts.update(rc); runs.update(rn)
            for k, v in tr.items():
                trials.setdefault(k, {}).update(v)
    return receipts, runs, trials


def known_digests():
    known = set()
    for name in ("discovery.jsonl.gz", "discovery-supplement.jsonl.gz"):
        path = REF / name
        if path.exists():
            with gzip.open(path, "rt") as f:
                for line in f:
                    known.add(json.loads(line)["digest"].removeprefix("sha256:"))
    return known


def write_gz(path, rows):
    with gzip.open(path, "wt") as f:
        for r in rows:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")


def identity_xet(members, xets):
    """Xet hash that identifies a trial's execution: its meter log, else its ATIF file."""
    for kind in ("meter", "trajectory"):
        m = members.get(kind)
        if m and m["bytes"] >= MIN_IDENTITY_BYTES and xets.get(kind):
            return kind, xets[kind]
    return None, None


def main():
    t0 = time.time()
    OUT.mkdir(exist_ok=True); CACHE.mkdir(exist_ok=True)
    receipt = json.loads((D.PLAN / "frozen.json").read_text())
    sealed = json.loads((REF / "sealed-tasks.json").read_text())["tasks"]
    where, batches = reconstruct(receipt)
    acks, status, problems = verify(batches)
    log("reconstructed", len(where), "objects in", len(batches), "planned shards", status)

    base_runs, base_identity = set(), set()
    with (ROOT / "frozen-identities.txt").open() as f:
        for line in f:
            path, xet = line.rstrip("\n").split("\t", 1)
            if path.startswith("runs/") and path.count("/") >= 2:
                base_runs.add(path.split("/")[1])
            if path.endswith(("/agent/hlb-meter.jsonl", "/agent/trajectory.json")):
                base_identity.add(xet)
    log("base runs", len(base_runs), "identity hashes", len(base_identity))

    delta_jobs = [("delta", D.GCS_PREFIX, a["archiveKey"]) for s, a in sorted(acks.items()) if a["phase"] == "core"]
    receipts, run_info, parsed = parse_shards(delta_jobs, sealed)
    log("parsed delta core shards", len(delta_jobs))
    base_ledger = json.loads((REF / "base-archive-ledger.json").read_text())
    base_jobs = [("base", BASE_PREFIX, s["archiveKey"]) for s in base_ledger if s["phase"] == "core"]
    _, base_info, base_trials = parse_shards(base_jobs, sealed)
    log("parsed base core shards", len(base_jobs))
    baseline = Counter(f'{t.get("harness") or "unknown"}@{t.get("harnessVersion") or "?"}' for t in base_trials.values())

    trials = defaultdict(lambda: dict(members={}, xets={}, companionObjects=0, companionBytes=0, shards=set()))
    runs = defaultdict(lambda: dict(objects=0, bytes=0))
    members = []
    for path, (serial, phase, size, xet) in where.items():
        run, trial, bench, tdir, rel = split(path)
        key = f"archive/shard-{serial:05d}.tar.zst"
        members.append(dict(path=path, size=size, xetHash=xet, run=run, trial=trial, phase=phase, shard=key,
                            sha256=receipts.get(path)))
        if run:
            runs[run]["objects"] += 1; runs[run]["bytes"] += size
        if not trial:
            continue
        t = trials[trial]
        t.update(run=run, benchmark=bench, trialDir=tdir, taskKey=task_of(tdir))
        t["shards"].add(key)
        if rel in TRIAL_FILES:
            kind = TRIAL_FILES[rel]
            t["members"][kind] = dict(bytes=size, shard=key, sha256=receipts.get(path), xetHash=xet)
            t["xets"][kind] = xet
        else:
            t["companionObjects"] += 1; t["companionBytes"] += size

    known = known_digests()
    single = {r: (i.get("harnesses") or list(i.get("harness_versions") or {})) for r, i in run_info.items()}
    first_seen = {}
    trial_rows = []
    # Earliest run first (run IDs start with a UTC timestamp), so the first holder of an identity is the original.
    for name, t in sorted(trials.items(), key=lambda kv: (kv[1]["run"], kv[0])):
        sealed_task = t["taskKey"] in sealed
        row = dict(trial=name, run=t["run"], benchmark=t["benchmark"], taskKey=t["taskKey"], sealedTask=sealed_task,
                   runInBase=t["run"] in base_runs, members=t["members"],
                   companionObjects=t["companionObjects"], companionBytes=t["companionBytes"], shards=sorted(t["shards"]))
        traj = t["members"].get("trajectory")
        if traj and traj.get("sha256"):
            row["atifDigest"] = traj["sha256"]
            row["atifInDiscoveryIndex"] = traj["sha256"] in known
        kind, ident = identity_xet(t["members"], t["xets"])
        row["identity"] = dict(kind=kind, xetHash=ident) if ident else None
        row["copiedFromBase"] = bool(ident and ident in base_identity)
        row["duplicateOf"] = first_seen.get(ident) if ident and not row["copiedFromBase"] else None
        if ident and ident not in first_seen:
            first_seen[ident] = name
        row["originalExecution"] = bool(ident) and not row["copiedFromBase"] and row["duplicateOf"] is None
        if not sealed_task:
            row.update(parsed.get(name, {}))
            if not row.get("harness"):
                declared = single.get(t["run"]) or []
                if len(declared) == 1:
                    row["harness"] = declared[0]
                    row["harnessVersion"] = ((run_info.get(t["run"]) or {}).get("harness_versions") or {}).get(declared[0])
                    row["harnessSource"] = "run.json"
        trial_rows.append(row)

    by_run = defaultdict(Counter)
    for x in trial_rows:
        c = by_run[x["run"]]
        c["trials"] += 1; c["sealed"] += x["sealedTask"]; c["original"] += x["originalExecution"]
        c["copiedFromBase"] += x["copiedFromBase"]; c["duplicates"] += x["duplicateOf"] is not None
        c["withResult"] += "result" in x["members"]; c["withMeter"] += "meter" in x["members"]
        if x["originalExecution"]:
            c["meterCalls"] += x.get("meterCalls") or 0
    run_rows = []
    for name, r in sorted(runs.items()):
        run_rows.append(dict(run=name, newRun=name not in base_runs, objects=r["objects"], bytes=r["bytes"],
                             **run_info.get(name, {}), **by_run.get(name, {})))

    hv = defaultdict(Counter)
    for x in trial_rows:
        if x["sealedTask"]:
            continue
        key = f'{x.get("harness") or "unknown"}@{x.get("harnessVersion") or "?"}'
        c = hv[key]
        c["trials"] += 1; c["original"] += x["originalExecution"]
        c["copiedFromBase"] += x["copiedFromBase"]; c["duplicates"] += x["duplicateOf"] is not None
        if x["originalExecution"]:
            c["meterCalls"] += x.get("meterCalls") or 0
    harness_rows = sorted(({"harnessVersion": k, **v, "baseTrials": baseline.get(k, 0)} for k, v in hv.items()),
                          key=lambda r: -r["trials"])
    summary = dict(
        schema="hlb-delta-catalog/v2", generatedAt=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        source=receipt["bucket"], base=receipt["base"], listingStarted=receipt["listingStarted"],
        bucketObserved=receipt["bucketObserved"], deltaObjects=receipt["objects"], deltaBytes=receipt["bytes"],
        listedObjects=receipt["listed"],
        verification=dict(status=status, mismatchedShards=problems, shardsPlanned=len(batches),
                          coreShardsRead=len(delta_jobs), baseCoreShardsRead=len(base_jobs)),
        runs=dict(total=len(run_rows), new=sum(r["newRun"] for r in run_rows),
                  baseWithLateObjects=sum(not r["newRun"] for r in run_rows)),
        trials=dict(total=len(trial_rows), sealedTask=sum(x["sealedTask"] for x in trial_rows),
                    inBaseRuns=sum(x["runInBase"] for x in trial_rows),
                    originalExecution=sum(x["originalExecution"] for x in trial_rows),
                    copiedFromBase=sum(x["copiedFromBase"] for x in trial_rows),
                    duplicateWithinDelta=sum(x["duplicateOf"] is not None for x in trial_rows),
                    withoutIdentity=sum(x["identity"] is None for x in trial_rows),
                    withTrajectory=sum("trajectory" in x["members"] for x in trial_rows),
                    withMeter=sum("meter" in x["members"] for x in trial_rows),
                    withResult=sum("result" in x["members"] for x in trial_rows),
                    atifAlreadyInDiscoveryIndex=sum(bool(x.get("atifInDiscoveryIndex")) for x in trial_rows)),
        harnessVersions=harness_rows,
        harnessVersionsNotInBase=[r["harnessVersion"] for r in harness_rows if r["baseTrials"] == 0],
        baseHarnessVersionTrials=dict(baseline.most_common()),
        elapsedSeconds=round(time.time() - t0))
    write_gz(OUT / "members.jsonl.gz", members)
    write_gz(OUT / "trials.jsonl.gz", trial_rows)
    (OUT / "runs.json").write_text(json.dumps(run_rows, indent=1))
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1))
    (OUT / "CATALOG.md").write_text(markdown(summary, run_rows))
    bucket = storage.Client().bucket(D.GCS_BUCKET)
    for f in ("members.jsonl.gz", "trials.jsonl.gz", "runs.json", "summary.json", "CATALOG.md"):
        bucket.blob(D.GCS_PREFIX + "catalog/" + f).upload_from_filename(str(OUT / f))
    log("CATALOG", json.dumps(dict(trials=summary["trials"], runs=summary["runs"])))


def markdown(s, runs):
    gb = lambda b: f"{b / 1e9:.1f} GB"
    v = s["verification"]
    lines = [
        "# Harness Leaderboard delta catalog", "",
        f"Generated {s['generatedAt']}. Source `{s['source']}`, listed from "
        f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(s['listingStarted']))} "
        f"(bucket updated {s['bucketObserved']['updatedAt']}). Base archive: `{s['base']}`.", "",
        f"The delta holds {s['deltaObjects']:,} objects ({gb(s['deltaBytes'])}) out of {s['listedObjects']:,} listed. "
        f"They span {s['runs']['new']} runs absent from the base archive and late objects in "
        f"{s['runs']['baseWithLateObjects']} of its runs.", "",
        f"Shard verification against acknowledgements: {json.dumps(v['status'])}. "
        f"Mismatched shards: {v['mismatchedShards'] or 'none'}.", "",
        "## Trials", "",
        "| Measure | Count |", "| --- | ---: |",
        *[f"| {k} | {n:,} |" for k, n in s["trials"].items()], "",
        "A copy has the same meter log (or ATIF file, without a meter log) as a base-archive object or a trial in an "
        "earlier delta run. Copies come from reused trials. Sealed-task trials keep paths, sizes, shards and digests "
        "only.", "",
        "## Harness versions (non-sealed trials)", "",
        "Harness and version come from each trial's config. Base counts use the same rule over the base archive's core shards.", "",
        "| Harness@version | Trials | Original executions | Copies of base | Duplicates in delta | Metered calls (original) | Base trials |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        *[f"| {r['harnessVersion']} | {r['trials']:,} | {r.get('original', 0):,} | {r.get('copiedFromBase', 0):,} | "
          f"{r.get('duplicates', 0):,} | {r.get('meterCalls', 0):,} | {r['baseTrials']:,} |" for r in s["harnessVersions"]], "",
        "## Runs", "",
        "| Run | New | Model | Harnesses | Trials | Original | Sealed | With result | Meter calls (original) | Size |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        *[f"| {r['run']} | {'yes' if r['newRun'] else 'late'} | {r.get('model') or ''} | "
          f"{', '.join(f'{h}@{ver}' for h, ver in (r.get('harness_versions') or {}).items())} | {r.get('trials', 0):,} | "
          f"{r.get('original', 0):,} | {r.get('sealed', 0):,} | {r.get('withResult', 0):,} | {r.get('meterCalls', 0):,} | "
          f"{gb(r['bytes'])} |" for r in runs],
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
