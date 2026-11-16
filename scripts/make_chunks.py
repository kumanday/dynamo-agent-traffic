#!/usr/bin/env python3
"""Split long runs into consecutive trial slices (by first call time) as units/chunk-<run>-cNN.jsonl.gz."""
import gzip, json, os, sys
from pathlib import Path
ROOT = Path(os.environ.get("FULL_ROOT", "full"))
n = int(sys.argv[1]); runs = sys.argv[2:]
for run in runs:
    trials = [json.loads(l) for l in gzip.open(ROOT / "meters" / f"{run}.jsonl.gz", "rt")]
    first = lambda t: min((c["ts"] for c in t["calls"] if c.get("status") == 200), default=float("inf"))
    trials.sort(key=lambda t: (first(t), t["trial"]))
    size = -(-len(trials) // n)
    for k in range(n):
        part = trials[k * size:(k + 1) * size]
        with gzip.open(ROOT / "units" / f"chunk-{run}-c{k:02d}.jsonl.gz", "wt") as f:
            for t in part:
                f.write(json.dumps(t, separators=(",", ":")) + "\n")
        print(run, k, len(part))
