#!/usr/bin/env python3
"""Tabulate provider prefix-cache hits against the append-only reusable prefix.

Reads the .stats.json sidecars that `hlb_to_agentic.py --stats-only` writes for
each run and aggregates them by harness version, served model and provider.
`providerCached` is the provider's own cached-token count from the meter log.
`upperReuse` is the prefix each call could reuse if the context only grows by
appending (the previous prompt of the same stream, or the harness's shared
prefix on a stream's first call). The shortfall is the reusable prefix the
provider recomputed.
"""
import argparse, glob, json
from collections import Counter, defaultdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stats_dir")
    ap.add_argument("--min-calls", type=int, default=2000)
    ap.add_argument("--by-run", action="store_true", help="one row per run instead of per harness/model/provider")
    a = ap.parse_args()

    agg, runs = defaultdict(Counter), defaultdict(set)
    for f in sorted(glob.glob(f"{a.stats_dir}/*.stats.json")):
        d = json.load(open(f))
        run = f.rsplit("/", 1)[-1].removesuffix(".stats.json")
        for k, v in d["byHarness"].items():
            h, served = k.split("|", 1)
            model, _, provider = served.partition(":")
            key = (h, model.split("/")[-1], provider or "(none)") + ((run,) if a.by_run else ())
            agg[key].update(v)
            runs[key].add(run)

    cols = ["Harness", "Model", "Provider"] + (["Run"] if a.by_run else []) + [
        "Trials", "Calls", "Mean prompt", "Provider cached", "Append-only reusable", "Recomputed reusable",
        "Calls short >=1k", "Runs"]
    print("| " + " | ".join(cols) + " |")
    print("| " + " | ".join(["---"] * (3 + a.by_run) + ["---:"] * 8) + " |")
    rows = [(k, v) for k, v in agg.items() if v["calls"] >= a.min_calls]
    rows.sort(key=lambda kv: (kv[0][0], -kv[1]["calls"]))
    for k, v in rows:
        cells = list(k) + [f"{v['plays']:,}", f"{v['calls']:,}", f"{v['input'] / v['calls']:,.0f}",
                           f"{v['providerCached'] / v['input']:.1%}", f"{v['upperReuse'] / v['input']:.1%}",
                           f"{v['providerShortfall'] / v['input']:.1%}", f"{v['callsShortfall'] / v['calls']:.1%}",
                           str(len(runs[k]))]
        print("| " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
