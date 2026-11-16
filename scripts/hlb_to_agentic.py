#!/usr/bin/env python3
"""Convert Harness Leaderboard meter logs to Dynamo agentic Mooncake v2 traces.

Input: one gzip JSONL file from extract_meters.py (one row per trial, with the
parsed agent/hlb-meter.jsonl calls). Output: an agentic Mooncake v2 JSONL trace
for `aisimulate predict --stack dynamo` and a JSON sidecar with conversion
statistics.

Each trial becomes one play and each successful metered call becomes one
request. Calls are grouped into streams: a call continues the idle stream whose
last prompt it extends, and otherwise forks a new stream from the best-matching
prompt (a parallel call, a subagent or a compaction). Each stream is its own
session.

Prompt blocks (`hash_ids`) are synthesized from token counts; no prompt text is
read. A call reuses the leading blocks of its parent prompt:

- `lower`: as many tokens as the provider reported cached, capped at the parent
  prompt. This is what the provider's own cache achieved.
- `upper`: the whole parent prompt when the call extends it (append-only
  context), else the harness's shared prefix. Never less than `lower`.

A trial's first call draws its reused blocks from one prefix chain shared by
every trial of the same harness version in the run: the system prompt and tool
definitions.

Dependencies: a stream's next call depends on the completion of its previous
call, delayed by the recorded gap (tool and harness time). A call that waited on
another stream's completion also joins it. A forked stream spawns from the
latest completed call, or from the dispatch of an in-flight call when it
started while every earlier call was still running.

Pacing: `closed` (default) releases each dependent request on its dependencies
alone, so a faster or slower simulated server moves the agent's next call with
it. `recorded` also holds each request until its recorded start offset.
"""
import argparse, gzip, hashlib, json, math, statistics
from collections import Counter, defaultdict
from pathlib import Path

SCHEMA = "dynamo.agentic_mooncake"
TOL_S = 0.05  # clock tolerance when deciding whether a call was still in flight


class Ids:
    def __init__(self, start=1):
        self.n = start

    def take(self, k):
        out = list(range(self.n, self.n + k))
        self.n += k
        return out


def blocks(tokens, bs):
    return math.ceil(tokens / bs)


def shared_prefix(calls_by_trial, mode):
    """Shared prefix length (tokens) per harness version, from first-call cached counts."""
    firsts = defaultdict(list)
    for h, calls in calls_by_trial:
        if calls:
            firsts[h].append(calls[0]["cached"])
    out = {}
    for h, v in firsts.items():
        pos = sorted(x for x in v if x > 0)
        if not pos:
            out[h] = 0
        elif mode == "lower":
            out[h] = pos[-1]  # chain long enough for every trial's own cached count
        else:
            out[h] = pos[int(0.9 * (len(pos) - 1))]
    return out


def convert_trial(t, play_idx, origin, args, ids, shared_chain, shared_len, shared_up, stats):
    calls = [c for c in t["calls"] if c.get("status") == 200 and int(c.get("input") or 0) > 0]
    if not calls:
        return []
    bs = args.block_size
    play_id = t["trial"].split("/", 1)[1]  # run/benchmark/trial
    h = f"{t.get('harness')}@{t.get('harnessVersion')}"
    model = t.get("modelName") or calls[0].get("model") or "unknown"
    served = calls[0].get("model") or model  # provider-qualified model id from the proxy log
    rows, done = [], []  # done: (end_ts, request_id, stream)
    streams = []  # each: {"sid", "chain", "len", "last_rid", "last_end", "busy_until"}
    root_nb = None

    for i, c in enumerate(calls):
        ts, lat = float(c["ts"]), float(c.get("latency_s") or 0.0)
        end = ts + lat
        inp, cached = int(c["input"]), int(c.get("cached") or 0)
        out_tok = max(1, int(c.get("output") or 0))
        rid = f"{play_idx:05d}-{i:05d}"

        # Parent prompt: the stream (busy or idle) with the longest prompt this call extends.
        best = None
        for s in streams:
            if s["len"] <= inp + bs and (best is None or s["len"] > best["len"]):
                best = s
        idle = best is not None and best["busy_until"] <= ts + TOL_S
        cont = idle and inp >= best["len"] - bs

        if best is None:  # first call, or a prompt shorter than every stream: compaction or new subagent
            parent_chain, parent_len = shared_chain[h], shared_len[h]
        else:
            parent_chain, parent_len = best["chain"], best["len"]
        lower = min(cached, parent_len, inp - 1)
        if best is not None and inp >= parent_len - bs:
            upper = max(lower, min(parent_len, inp - 1))
        else:
            upper = max(lower, min(shared_up[h], inp - 1))
        reuse = lower if args.hashes == "lower" else upper
        nreuse = min(reuse // bs, len(parent_chain))
        nblk = blocks(inp, bs)
        chain = parent_chain[:nreuse] + ids.take(nblk - nreuse)
        hs = stats["byHarness"][f"{h}|{served}"]
        for k, v in (("calls", 1), ("input", inp), ("output", out_tok), ("providerCached", cached),
                     ("lowerReuse", lower), ("upperReuse", upper), ("traceReuse", nreuse * bs),
                     ("providerShortfall", max(0, upper - cached)),
                     ("callsShortfall", int(upper - cached >= args.shortfall_tokens))):
            hs[k] += v
            stats[k] += v

        deps = []
        if cont:
            s = best
            deps.append(dict(request_id=s["last_rid"], trigger="completion",
                             delay_ms=round(max(0.0, ts - s["last_end"]) * 1000, 3), relation="sequence"))
            # Joined another stream that completed after this stream's previous call.
            others = [d for d in done if d[2] is not s and s["last_end"] < d[0] <= ts + TOL_S]
            if others:
                e, orid, _ = max(others, key=lambda d: d[0])
                deps.append(dict(request_id=orid, trigger="completion",
                                 delay_ms=round(max(0.0, ts - e) * 1000, 3), relation="join"))
                stats["joins"] += 1
        else:
            s = {"sid": f"{play_id}#s{len(streams)}"}
            streams.append(s)
            if rows:
                finished = [d for d in done if d[0] <= ts + TOL_S]
                if finished:
                    e, orid, _ = max(finished, key=lambda d: d[0])
                    deps.append(dict(request_id=orid, trigger="completion",
                                     delay_ms=round(max(0.0, ts - e) * 1000, 3), relation="spawn"))
                else:  # started while every earlier call was in flight
                    prev = rows[-1]
                    deps.append(dict(request_id=prev["request_id"], trigger="dispatch",
                                     delay_ms=round(max(0.0, ts - prev["_ts"]) * 1000, 3), relation="spawn"))
                stats["forks"] += 1
                if best is not None and best["busy_until"] > ts + TOL_S:
                    stats["parallelForks"] += 1
                elif best is None:
                    stats["resets"] += 1
        s.update(chain=chain, len=inp, last_rid=rid, last_end=end, busy_until=end)

        nb = round((ts - origin) * 1000, 3)
        if root_nb is None:
            root_nb = nb
        row = dict(request_id=rid, play_id=play_id, source_play_ordinal=play_idx, session_id=s["sid"],
                   model=model, input_length=inp, output_length=out_tok,
                   hash_ids=chain, not_before_ms=nb if (not deps or args.pacing == "recorded") else root_nb,
                   recorded_api_time_ms=round(lat * 1000, 3), dependencies=deps, _ts=ts)
        rows.append(row)
        done.append((end, rid, s))
    stats["streams"] += len(streams)
    stats["byHarness"][f"{h}|{served}"]["plays"] += 1
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("meters", help="per-run gzip JSONL from extract_meters.py")
    ap.add_argument("out", help="output trace path (.jsonl)")
    ap.add_argument("--hashes", choices=("lower", "upper"), default="lower")
    ap.add_argument("--pacing", choices=("closed", "recorded"), default="closed")
    ap.add_argument("--block-size", type=int, default=64)
    ap.add_argument("--harness", action="append", help="keep only these harness@version values")
    ap.add_argument("--start-hours", type=float, default=0.0, help="keep trials whose first call starts at or after this offset")
    ap.add_argument("--hours", type=float, help="window length from --start-hours, by trial start")
    ap.add_argument("--max-plays", type=int)
    ap.add_argument("--stats-only", action="store_true", help="write only the .stats.json sidecar")
    ap.add_argument("--shortfall-tokens", type=int, default=1024,
                    help="count a call when the provider cached at least this many tokens fewer than the append-only prefix")
    a = ap.parse_args()

    raw = Path(a.meters).read_bytes()
    trials = [json.loads(l) for l in gzip.decompress(raw).splitlines() if l.strip()]
    trials = [t for t in trials if any(c.get("status") == 200 for c in t["calls"])]
    if a.harness:
        trials = [t for t in trials if f"{t.get('harness')}@{t.get('harnessVersion')}" in a.harness]
    first = lambda t: min(c["ts"] for c in t["calls"] if c.get("status") == 200)
    trials.sort(key=lambda t: (first(t), t["trial"]))
    t0 = first(trials[0])
    trials = [t for t in trials if first(t) - t0 >= a.start_hours * 3600
              and (a.hours is None or first(t) - t0 < (a.start_hours + a.hours) * 3600)]
    if a.max_plays:
        trials = trials[:a.max_plays]
    origin = first(trials[0])

    ok = lambda t: [c for c in t["calls"] if c.get("status") == 200 and int(c.get("input") or 0) > 0]
    hv = lambda t: f"{t.get('harness')}@{t.get('harnessVersion')}"
    firsts = [(hv(t), ok(t)) for t in trials]
    shared_low, shared_up = shared_prefix(firsts, "lower"), shared_prefix(firsts, "upper")
    shared_len = {h: max(shared_low[h], shared_up[h]) for h in shared_low}
    ids = Ids()
    shared_chain = {h: ids.take(n // a.block_size) for h, n in shared_len.items()}

    stats = Counter(); stats["byHarness"] = defaultdict(Counter)
    rows = []
    for k, t in enumerate(trials):
        rows += convert_trial(t, k, origin, a, ids, shared_chain, shared_len, shared_up, stats)

    header = dict(schema=SCHEMA, version=2, block_size=a.block_size, hash_id_scope="local",
                  source=dict(format="harness_leaderboard_hlb_meter", digest="sha256:" + hashlib.sha256(raw).hexdigest()))
    if not a.stats_only:
        with open(a.out, "w") as f:
            f.write(json.dumps(header, separators=(",", ":")) + "\n")
            for r in rows:
                r.pop("_ts")
                f.write(json.dumps(r, separators=(",", ":")) + "\n")

    starts = sorted((first(t), max(c["ts"] + c.get("latency_s", 0) for c in ok(t))) for t in trials)
    ev = sorted([(s, 1) for s, _ in starts] + [(e, -1) for _, e in starts]); cur = peak = 0
    for _, d in ev:
        cur += d; peak = max(peak, cur)
    side = dict(source=a.meters, trace=a.out, hashes=a.hashes, pacing=a.pacing, blockSize=a.block_size,
                plays=len(trials), requests=len(rows), peakConcurrentPlays=peak,
                spanHours=round((max(e for _, e in starts) - origin) / 3600, 3),
                inputTokens=stats["input"], outputTokens=stats["output"], providerCachedTokens=stats["providerCached"],
                reusedTokens=stats["traceReuse"], lowerReuseTokens=stats["lowerReuse"], upperReuseTokens=stats["upperReuse"],
                providerCachedRatio=round(stats["providerCached"] / stats["input"], 4),
                traceReuseRatio=round(stats["traceReuse"] / stats["input"], 4),
                upperReuseRatio=round(stats["upperReuse"] / stats["input"], 4),
                providerShortfallTokens=stats["providerShortfall"], callsWithShortfall=stats["callsShortfall"],
                streams=stats["streams"], forks=stats["forks"], parallelForks=stats["parallelForks"],
                resets=stats["resets"], joins=stats["joins"],
                sharedPrefixTokens=dict(lower=shared_low, upper=shared_up),
                byHarness={h: dict(v) for h, v in stats["byHarness"].items()},
                model=sorted({str(t.get("modelName")) for t in trials}),
                meanInput=round(statistics.mean(r["input_length"] for r in rows)),
                medianInput=statistics.median(r["input_length"] for r in rows),
                meanOutput=round(statistics.mean(r["output_length"] for r in rows)),
                header=header)
    Path(a.out).with_suffix(".stats.json").write_text(json.dumps(side, indent=1))
    print(json.dumps({k: v for k, v in side.items() if k != "header"}, indent=1))


if __name__ == "__main__":
    main()
