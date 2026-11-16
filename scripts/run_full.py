#!/usr/bin/env python3
"""Full-dataset Dynamo replay: convert every run's meter file and replay it under each router policy.

Steps (each resumable):

  convert   meters/<unit>.jsonl.gz -> traces/<unit>.jsonl (+ .stats.json), upper-bound hashes, closed pacing
  replay    one `aisimulate predict --stack dynamo` per (unit, policy) at the unit's sized worker count
  collect   results/<unit>/<policy>/summary.json from each prediction.json; per-request records zstd-compressed

A unit is one leaderboard run, or one endpoint window (merged runs) under units/<name>.jsonl.gz.
Workers per unit: max(--min-workers, ceil(peak concurrent trials / --trials-per-worker)), on the base
configuration's worker shape. The minimum keeps a routing decision in every replay (one 8-GPU node of TP2
workers by default). Policies: rr (round-robin), kv (KV router defaults), kvp16 (KV router, prefill_load_scale 16),
aff (KV router with session affinity, TTL 300 s).
"""
import argparse, gzip, json, math, os, subprocess, sys, time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("FULL_ROOT", "full"))
HERE = Path(__file__).resolve().parent
POLICIES = {
    "rr": ["--set", "router.policy=round_robin"],
    "kv": ["--set", "router.policy=kv_router"],
    "kvp16": ["--set", "router.policy=kv_router", "--set", "router.prefill_load_scale=16"],
    "aff": ["--set", "router.policy=kv_router", "--set", "router.conversation_affinity={mode: session, ttl_seconds: 300}"],
}
KEEP = ["completed_requests", "num_requests", "incomplete_trajectories", "completed_trajectories",
        "prefix_cache_reused_ratio", "first_admission_prefix_cache_reused_ratio", "committed_prefill_tokens",
        "mean_ttft_ms", "median_ttft_ms", "p90_ttft_ms", "p99_ttft_ms", "max_ttft_ms", "mean_itl_ms", "p99_itl_ms",
        "mean_e2e_latency_ms", "p99_e2e_latency_ms", "mean_trajectory_e2e_latency_ms", "p50_trajectory_e2e_latency_ms",
        "p90_trajectory_e2e_latency_ms", "goodput_completed_requests", "duration_ms", "gpu_hours",
        "output_throughput_tok_s", "input_throughput_tok_s"]


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def units(args):
    src = [(p.name.removesuffix(".jsonl.gz"), p) for p in sorted((ROOT / "meters").glob("*.jsonl.gz"))]
    src += [(p.name.removesuffix(".jsonl.gz"), p) for p in sorted((ROOT / "units").glob("*.jsonl.gz"))]
    if args.only:
        src = [u for u in src if any(o in u[0] for o in args.only)]
    if args.exclude:
        src = [u for u in src if not any(o in u[0] for o in args.exclude)]
    return src


def complete(name, policies):
    return all((ROOT / "results" / name / p / "summary.json").exists() for p in policies)


def convert_one(job):
    name, path, policies = job
    out = ROOT / "traces" / f"{name}.jsonl"
    stats = out.with_suffix(".stats.json")
    if stats.exists() and (out.exists() or complete(name, policies)):
        return name, json.loads(stats.read_text())
    r = subprocess.run([sys.executable, str(HERE / "hlb_to_agentic.py"), str(path), str(out), "--hashes", "upper"],
                       capture_output=True, text=True)
    if r.returncode:
        return name, {"error": r.stderr[-2000:]}
    return name, json.loads(stats.read_text())


def workers_for(stats, per_worker, minimum):
    return max(minimum, math.ceil(stats["peakConcurrentPlays"] / per_worker))


def replay_one(job):
    name, policy, workers, base, capture = job
    out = ROOT / "results" / name / policy
    if (out / "summary.json").exists():
        return name, policy, "cached"
    out.mkdir(parents=True, exist_ok=True)
    (out / "failed").unlink(missing_ok=True)
    cfg = yaml.safe_load(Path(base).read_text())
    # Many replays start together; trace parsing can exceed the 60 s default before the engine reports ready.
    cfg.setdefault("execution", {}).setdefault("resources", {})["initialization_timeout_seconds"] = 1800
    cfg["traffic"]["source"]["paths"] = [str(ROOT / "traces" / f"{name}.jsonl")]
    cfg["engine"]["workers"]["aggregated"]["parallelism"]["replicas"] = workers
    (out / "config.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))
    t0 = time.time()
    cmd = ["aisimulate", "predict", "--stack", "dynamo", "--config", str(out / "config.yaml"), "--output-dir", str(out),
           "--overwrite", *(["--capture-per-request"] if capture else []), "--format", "json", *POLICIES[policy]]
    with open(out / "stderr.log", "w") as err, open(out / "stdout.json", "w") as so:
        rc = subprocess.run(cmd, stdout=so, stderr=err).returncode
    pred = out / "prediction.json"
    if rc or not pred.exists():
        (out / "failed").write_text(f"exit {rc}\n")
        return name, policy, f"failed {rc}"
    s = json.loads(pred.read_text())["summary"]
    summary = dict(unit=name, policy=policy, workers=workers, wallSeconds=round(time.time() - t0, 1),
                   **{k: s.get(k) for k in KEEP})
    req = out / "requests.jsonl"
    if req.exists():
        subprocess.run(["zstd", "-q", "-10", "--rm", "-f", str(req)], check=False)
    pred_small = json.loads(pred.read_text())
    pred_small.pop("per_request", None)
    (out / "prediction.json").write_text(json.dumps(pred_small))
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    return name, policy, f"ok {summary['wallSeconds']}s"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=str(HERE / "sim" / "glm-b300-op.yaml"))
    ap.add_argument("--policies", default="rr,kv,kvp16,aff")
    ap.add_argument("--trials-per-worker", type=float, default=50)
    ap.add_argument("--workers", type=int, default=40, help="parallel replays")
    ap.add_argument("--stagger", type=float, default=2.0, help="seconds between the first --workers launches")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--exclude", nargs="*")
    ap.add_argument("--min-workers", type=int, default=4)
    ap.add_argument("--capture", action="store_true", help="keep per-request records (zstd)")
    ap.add_argument("--keep-traces", action="store_true")
    ap.add_argument("--convert-only", action="store_true")
    a = ap.parse_args()
    for d in ("traces", "results"):
        (ROOT / d).mkdir(exist_ok=True)

    us = units(a)
    log(f"converting {len(us)} units")
    stats = {}
    with ProcessPoolExecutor(a.workers) as pool:
        for name, st in pool.map(convert_one, [(n, p, a.policies.split(",")) for n, p in us]):
            stats[name] = st
            if "error" in st:
                log("convert failed", name, st["error"][-300:])
    merged = json.loads((ROOT / "unit-stats.json").read_text()) if (ROOT / "unit-stats.json").exists() else {}
    merged.update(stats)
    (ROOT / "unit-stats.json").write_text(json.dumps(merged, indent=1))
    if a.convert_only:
        log("converted; stats in unit-stats.json")
        return
    plan = []
    for name, st in stats.items():
        if "error" in st or not st.get("requests"):
            continue
        w = workers_for(st, a.trials_per_worker, a.min_workers)
        for p in a.policies.split(","):
            plan.append((name, p, w, a.base, a.capture))
    # Longest jobs first: requests times workers approximates simulation cost.
    plan.sort(key=lambda j: -stats[j[0]]["requests"] * (1 + 0.15 * j[2]))
    (ROOT / f"plan-{int(time.time())}.json").write_text(json.dumps([dict(unit=n, policy=p, workers=w) for n, p, w, *_ in plan], indent=1))
    log(f"{len(plan)} replays over {len(stats)} units; {sum(s.get('requests', 0) for s in stats.values()):,} requests per policy")

    policies = a.policies.split(",")
    remaining = {}
    for n, *_ in plan:
        remaining[n] = remaining.get(n, 0) + 1
    done, queue, running, launched = 0, list(plan), set(), 0
    with ProcessPoolExecutor(a.workers) as pool:
        while queue or running:
            while queue and len(running) < a.workers:
                running.add(pool.submit(replay_one, queue.pop(0)))
                launched += 1
                if launched <= a.workers:
                    time.sleep(a.stagger)
            finished, running = wait(running, return_when=FIRST_COMPLETED)
            for f in finished:
                name, policy, status = f.result()
                done += 1
                remaining[name] -= 1
                log(f"[{done}/{len(plan)}] {name} {policy} {status}")
                if remaining[name] == 0 and complete(name, policies) and not a.keep_traces:
                    (ROOT / "traces" / f"{name}.jsonl").unlink(missing_ok=True)
    log("all replays finished")


if __name__ == "__main__":
    main()
