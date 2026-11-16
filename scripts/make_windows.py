#!/usr/bin/env python3
"""Merge runs that loaded the same endpoint at the same time into endpoint-window units.

The endpoint is the provider-qualified model id from the proxy log, with client
route prefixes (`openai/`, `hlb/`) removed. Runs on one endpoint whose active
spans (first call start to last call end) overlap form a connected component;
each component with at least two runs becomes units/<endpoint-slug>-<start>.jsonl.gz,
holding every original trial of those runs. windows.json lists them.
"""
import argparse, datetime, gzip, json, os, re
from collections import defaultdict
from pathlib import Path

ROOT = Path(os.environ.get("FULL_ROOT", "full"))


def endpoint(model):
    m = model or "?"
    for p in ("openai/", "hlb/"):
        m = m.removeprefix(p)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-runs", type=int, default=2)
    a = ap.parse_args()
    spans = defaultdict(list)  # endpoint -> [(start, end, run, path)]
    for p in sorted((ROOT / "meters").glob("*.jsonl.gz")):
        start = end = None; models = defaultdict(int)
        for line in gzip.open(p, "rt"):
            t = json.loads(line)
            calls = [c for c in t["calls"] if c.get("status") == 200]
            if not calls:
                continue
            models[endpoint(calls[0].get("model"))] += 1
            s, e = calls[0]["ts"], max(c["ts"] + c.get("latency_s", 0) for c in calls)
            start = s if start is None else min(start, s); end = e if end is None else max(end, e)
        if start is None:
            continue
        ep = max(models, key=models.get)
        spans[ep].append((start, end, p.name.removesuffix(".jsonl.gz"), p))
    (ROOT / "units").mkdir(exist_ok=True)
    windows = []
    for ep, rows in spans.items():
        rows.sort()
        comp, comp_end = [], None
        groups = []
        for s, e, run, p in rows:
            if comp and s <= comp_end:
                comp.append((s, e, run, p)); comp_end = max(comp_end, e)
            else:
                if comp:
                    groups.append(comp)
                comp, comp_end = [(s, e, run, p)], e
        if comp:
            groups.append(comp)
        for g in groups:
            if len(g) < a.min_runs:
                continue
            start = datetime.datetime.fromtimestamp(g[0][0], datetime.UTC).strftime("%Y%m%d-%H%M")
            name = "endpoint-" + re.sub(r"[^a-z0-9]+", "-", ep.lower()).strip("-") + "-" + start
            trials = []
            for _, _, run, p in g:
                trials += [json.loads(l) for l in gzip.open(p, "rt")]
            trials = [t for t in trials if endpoint(next((c.get("model") for c in t["calls"] if c.get("status") == 200), None)) == ep]
            with gzip.open(ROOT / "units" / f"{name}.jsonl.gz", "wt") as f:
                for t in sorted(trials, key=lambda t: (min((c["ts"] for c in t["calls"]), default=0), t["trial"])):
                    f.write(json.dumps(t, separators=(",", ":")) + "\n")
            windows.append(dict(unit=name, endpoint=ep, runs=[r for _, _, r, _ in g], trials=len(trials),
                                start=g[0][0], end=max(e for _, e, _, _ in g)))
    (ROOT / "units" / "windows.json").write_text(json.dumps(windows, indent=1))
    for w in windows:
        print(w["unit"], len(w["runs"]), w["trials"])


if __name__ == "__main__":
    main()
