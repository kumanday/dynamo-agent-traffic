#!/usr/bin/env python3
"""Provider cache hits over time per served endpoint, next to active agent trials.

Reads extract_meters.py output (one gzip JSONL per run). For each endpoint (the
proxy log's provider-qualified model id) and time bucket it reports the number
of trials with a call in flight or between calls, the provider's cached share
of prompt tokens, and an append-only estimate of the reusable share (each call
can reuse its trial's previous prompt when the prompt grew). Only the trials
extract_meters.py selects are counted (original executions in the delta archive,
outside the sealed tasks), so active-trial counts are a lower bound on the
endpoint's real concurrency.
"""
import argparse, datetime, glob, gzip, json
from collections import Counter, defaultdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("meters_dir")
    ap.add_argument("--endpoint", action="append", help="substring of the served model id; repeatable")
    ap.add_argument("--bucket-minutes", type=int, default=30)
    ap.add_argument("--min-calls", type=int, default=200)
    a = ap.parse_args()
    B = a.bucket_minutes * 60

    buckets = defaultdict(lambda: defaultdict(Counter))
    spans = defaultdict(list)
    for f in sorted(glob.glob(f"{a.meters_dir}/*.jsonl.gz")):
        run = f.rsplit("/", 1)[-1].removesuffix(".jsonl.gz")
        for line in gzip.open(f, "rt"):
            t = json.loads(line)
            calls = [c for c in t["calls"] if c.get("status") == 200 and c.get("input")]
            if not calls:
                continue
            ep = calls[0].get("model", "?")
            if a.endpoint and not any(e in ep for e in a.endpoint):
                continue
            spans[ep].append((calls[0]["ts"], calls[-1]["ts"] + calls[-1].get("latency_s", 0)))
            prev = None
            for c in calls:
                r = buckets[ep][int(c["ts"] // B) * B]
                r["calls"] += 1; r["input"] += c["input"]; r["cached"] += c.get("cached", 0)
                if prev and c["input"] >= prev:
                    r["reusable"] += prev
                prev = c["input"]
                r["run:" + run] += 1

    for ep in sorted(buckets):
        print(f"\n### {ep}\n")
        print("| Bucket start (UTC) | Active trials | Calls | Provider cached | Reusable (append-only) | Runs |")
        print("| --- | ---: | ---: | ---: | ---: | --- |")
        for b in sorted(buckets[ep]):
            r = buckets[ep][b]
            if r["calls"] < a.min_calls:
                continue
            active = sum(1 for s, e in spans[ep] if s < b + B and e > b)
            runs = ", ".join(sorted(k[4:] for k in r if k.startswith("run:")))
            when = datetime.datetime.fromtimestamp(b, datetime.UTC).strftime("%Y-%m-%d %H:%M")
            print(f"| {when} | {active} | {r['calls']:,} | {r['cached'] / r['input']:.1%} | "
                  f"{r['reusable'] / r['input']:.1%} | {runs} |")


if __name__ == "__main__":
    main()
