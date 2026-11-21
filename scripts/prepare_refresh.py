#!/usr/bin/env python3
"""Prepare a refreshed replay root (FULL_ROOT) from a previous pass (OLD_ROOT).

  select  keep endpoint windows by rule, move the rest to units/unused; reuse old replays of unchanged units
  plan    after `run_full.py --convert-only`: predict replay time, slice long runs, list the replays to run

Window rule (it reproduces the 13 windows the first pass chose by hand): merged peak concurrency at least
1.5 times the busiest member run's peak, a merged peak of at least 60 trials and a span of at most 36 hours;
plus every flint window. A unit reuses the old replays when its original trials are identical: an unchanged
run, a window with the same runs and trials, a slice or check unit of an unchanged run.
Predicted replay seconds = 90 x (simulated span hours + million output tokens), fitted on the 916 old replays.
"""
import gzip, json, math, os, shutil, subprocess, sys
from pathlib import Path

OLD = Path(os.environ["OLD_ROOT"])
NEW = Path(os.environ.get("FULL_ROOT", "full"))
REF = Path(os.environ.get("REFRESH_DIR", "refresh"))  # index_bucket.py output under REF/index, window_table.py output in REF
POLICIES = ("rr", "kv", "kvp16", "aff")


def complete(root, unit):
    return all((root / "results" / unit / p / "summary.json").exists() for p in POLICIES)


def reuse(unit, src_unit_file=None):
    if not complete(OLD, unit):
        return False
    if (NEW / "results" / unit).exists():
        shutil.rmtree(NEW / "results" / unit)
    shutil.copytree(OLD / "results" / unit, NEW / "results" / unit)
    shutil.copy(OLD / "traces" / f"{unit}.stats.json", NEW / "traces" / f"{unit}.stats.json")
    if src_unit_file:
        shutil.copy(src_unit_file, NEW / "units" / src_unit_file.name)
    return True


def select():
    (NEW / "units" / "unused").mkdir(parents=True, exist_ok=True)
    (NEW / "results").mkdir(exist_ok=True); (NEW / "traces").mkdir(exist_ok=True)
    table = json.loads((REF / "window-table.json").read_text())
    diff = json.loads((REF / "index" / "runs-diff.json").read_text())
    unchanged = {r for r, v in diff.items() if v["status"] == "unchanged"}
    chosen, reused = [], []
    for w in table:
        keep = "flint" in w["endpoint"].lower() or (w["ratio"] >= 1.5 and w["windowPeak"] >= 60 and w["spanHours"] <= 36)
        w["selected"] = keep
        f = NEW / "units" / f"{w['unit']}.jsonl.gz"
        if not keep:
            f.rename(NEW / "units" / "unused" / f.name)
            continue
        chosen.append(w["unit"])
        if w["sameAsOld"] and w["oldUsed"] and reuse(w["unit"]):
            reused.append(w["unit"])
    (REF / "window-selection.json").write_text(json.dumps(table, indent=1))
    runs_reused = [r for r in sorted(unchanged) if (NEW / "meters" / f"{r}.jsonl.gz").exists() and reuse(r)]
    extra = []
    for p in sorted((OLD / "units").glob("*.jsonl.gz")):
        name = p.name.removesuffix(".jsonl.gz")
        if name.startswith("chunk-"):
            parent = name.removeprefix("chunk-").rsplit("-c", 1)[0]
        elif name.startswith("dsvcheck-"):
            parent = name.removeprefix("dsvcheck-")
        else:
            continue
        if parent in unchanged and reuse(name, p):
            extra.append(name)
    out = dict(windowsSelected=chosen, windowsReused=reused, runsReused=len(runs_reused), sliceAndCheckReused=extra)
    (REF / "reuse.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in out.items()}))


def plan(target_s=2400.0, slice_s=1800.0):
    stats = json.loads((NEW / "unit-stats.json").read_text())
    units = [p.name.removesuffix(".jsonl.gz") for p in sorted((NEW / "meters").glob("*.jsonl.gz"))]
    units += [p.name.removesuffix(".jsonl.gz") for p in sorted((NEW / "units").glob("*.jsonl.gz"))]
    pred = lambda s: 90 * (s["spanHours"] + s["outputTokens"] / 1e6)
    todo, sliced = [], {}
    for u in units:
        if complete(NEW, u) or u.startswith("dsvcheck-") or any((NEW / "units").glob(f"chunk-{u}-c*.jsonl.gz")):
            continue
        s = stats.get(u)
        if not s or "error" in s or not s.get("requests"):
            continue
        if not u.startswith(("endpoint-", "chunk-")) and pred(s) > target_s:
            n = min(12, math.ceil(pred(s) / slice_s))
            sliced[u] = n
            continue
        todo.append(dict(unit=u, predicted=round(pred(s)), requests=s["requests"]))
    for u, n in sliced.items():
        subprocess.run([sys.executable, str(Path(__file__).with_name("make_chunks.py")), str(n), u], check=True,
                       env=os.environ | {"FULL_ROOT": str(NEW)})
    if sliced:
        prev = json.loads((REF / "sliced.json").read_text()) if (REF / "sliced.json").exists() else {}
        (REF / "sliced.json").write_text(json.dumps(prev | sliced, indent=1))
    (REF / "plan-units.json").write_text(json.dumps(todo, indent=1))
    print(json.dumps(dict(unitsToReplay=len(todo), predictedReplaySeconds=sum(t["predicted"] for t in todo) * 4,
                          longest=sorted(todo, key=lambda t: -t["predicted"])[:5], sliced=sliced)))


if __name__ == "__main__":
    {"select": select, "plan": plan}[sys.argv[1]]()
