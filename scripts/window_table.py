#!/usr/bin/env python3
"""Window table for ROOT (after make_windows.py): merged peak, busiest member run's peak, span, and
whether a previous pass (OLD, or -) replayed a window of the same name and runs.
Usage: window_table.py ROOT OLD > table.json"""
import gzip, json, sys
from pathlib import Path
root, old = Path(sys.argv[1]), Path(sys.argv[2])


def spans(path):
    out = []
    for line in gzip.open(path, "rt"):
        t = json.loads(line)
        c = [x for x in t["calls"] if x.get("status") == 200]
        if c:
            out.append((c[0]["ts"], max(x["ts"] + x.get("latency_s", 0) for x in c)))
    return out


def peak(sp):
    ev = sorted([(s, 1) for s, _ in sp] + [(e, -1) for _, e in sp])
    cur = best = 0
    for _, d in ev:
        cur += d; best = max(best, cur)
    return best


has_old = str(old) != "-" and (old / "units" / "windows.json").exists()
old_w = {w["unit"]: w for w in json.loads((old / "units" / "windows.json").read_text())} if has_old else {}
old_used = {p.name.removesuffix(".jsonl.gz") for p in (old / "units").glob("endpoint-*.jsonl.gz")} if has_old else set()
run_peak, rows = {}, []
for w in json.loads((root / "units" / "windows.json").read_text()):
    for r in w["runs"]:
        if r not in run_peak:
            run_peak[r] = peak(spans(root / "meters" / f"{r}.jsonl.gz"))
    wp = peak(spans(root / "units" / f"{w['unit']}.jsonl.gz"))
    mx = max(run_peak[r] for r in w["runs"])
    o = old_w.get(w["unit"])
    rows.append(dict(unit=w["unit"], endpoint=w["endpoint"], runs=w["runs"], trials=w["trials"], windowPeak=wp,
                     maxRunPeak=mx, ratio=round(wp / max(mx, 1), 2), spanHours=round((w["end"] - w["start"]) / 3600, 1),
                     sameAsOld=bool(o) and o["runs"] == w["runs"] and o["trials"] == w["trials"], oldUsed=w["unit"] in old_used))
print(json.dumps(rows, indent=1))
