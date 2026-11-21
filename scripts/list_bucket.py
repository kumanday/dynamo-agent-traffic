#!/usr/bin/env python3
"""List what the replay needs from every run in the public Harness Leaderboard bucket.

For each run: list the run folder and each benchmark folder one level deep to find trial folders, then
ask paths-info (1,000 paths per request) for each trial's agent/hlb-meter.jsonl and config.json, and for
agent/trajectory.json where the meter log is missing or under 256 bytes. This takes a few requests per
run instead of walking every object. Anonymous requests are limited to 500 per five minutes per IP;
the library and the retry loop wait out the limit. Resumable: a run with a .done marker is skipped.

Writes OUT/listing/<run>.jsonl.gz (path, size, xetHash) and OUT/listing/bucket.json (run list, listing
start and end, bucket updatedAt and totalFiles).
Usage: list_bucket.py OUT [PRIORITY_RUNS_JSON [reverse]]
"""
import gzip, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import urlopen
from huggingface_hub import BucketFile, BucketFolder, get_bucket_paths_info, list_bucket_tree

BUCKET = "joelniklaus/harness-leaderboard"
OUT = Path(sys.argv[1]) / "listing"


def retry(fn):
    for attempt in range(10):
        try:
            return fn()
        except Exception as e:
            if attempt == 9:
                raise
            print("RETRY", type(e).__name__, str(e)[:120], flush=True)
            time.sleep(min(300, 20 * 2 ** attempt))


def info():
    with urlopen("https://huggingface.co/api/buckets/" + BUCKET, timeout=30) as r:
        d = json.load(r)
    return {k: d.get(k) for k in ("updatedAt", "size", "totalFiles")}


def row(o):
    return dict(path=o.path, size=o.size, xetHash=o.xet_hash)


def list_run(run):
    done = OUT / f"{run}.done"
    if done.exists():
        return run, int(done.read_text())
    top = retry(lambda: list(list_bucket_tree(BUCKET, prefix=f"runs/{run}", recursive=False, token=False)))
    rows = [row(o) for o in top if isinstance(o, BucketFile)]
    trials = []
    for bench in [o.path for o in top if isinstance(o, BucketFolder)]:
        items = retry(lambda: list(list_bucket_tree(BUCKET, prefix=bench, recursive=False, token=False)))
        rows += [row(o) for o in items if isinstance(o, BucketFile)]
        trials += [o.path for o in items if isinstance(o, BucketFolder)]
    want = [f"{t}/{rel}" for t in trials for rel in ("agent/hlb-meter.jsonl", "config.json")]
    got = retry(lambda: [row(o) for o in get_bucket_paths_info(BUCKET, want, token=False)]) if want else []
    meter = {r["path"].rsplit("/agent/", 1)[0]: r for r in got if r["path"].endswith("/agent/hlb-meter.jsonl")}
    weak = [f"{t}/agent/trajectory.json" for t in trials if t not in meter or meter[t]["size"] < 256]
    if weak:
        got += retry(lambda: [row(o) for o in get_bucket_paths_info(BUCKET, weak, token=False)])
    rows += got
    tmp = OUT / f"{run}.jsonl.gz.tmp"
    with gzip.open(tmp, "wt") as f:
        for r in rows:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")
    os.replace(tmp, OUT / f"{run}.jsonl.gz")
    (OUT / f"{run}.trials").write_text(str(len(trials)))
    done.write_text(str(len(rows)))
    return run, len(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if not (OUT / "bucket.json").exists():
        runs = sorted(x.path.split("/")[1] for x in retry(lambda: list(list_bucket_tree(BUCKET, prefix="runs", recursive=False, token=False)))
                      if isinstance(x, BucketFolder))
        (OUT / "bucket.json").write_text(json.dumps(dict(bucket=BUCKET, listingStarted=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                                         before=info(), runs=runs), indent=1))
    m = json.loads((OUT / "bucket.json").read_text())
    order = list(m["runs"])
    if len(sys.argv) > 2:
        first = set(json.loads(Path(sys.argv[2]).read_text()))
        order.sort(key=lambda r: (r not in first, r))
    if len(sys.argv) > 3 and sys.argv[3] == "reverse":  # a second lister works from the other end
        order.reverse()
    total = 0
    with ThreadPoolExecutor(4) as pool:
        for i, (run, n) in enumerate(pool.map(list_run, order), 1):
            total += n
            if i % 10 == 0:
                print(time.strftime("%H:%M:%S"), f"{i}/{len(order)} runs", flush=True)
    m.update(listingFinished=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), after=info(),
             method="list_bucket.py: folders plus paths-info")
    (OUT / "bucket.json").write_text(json.dumps(m, indent=1))
    print("LISTED", len(order), "runs", flush=True)


if __name__ == "__main__":
    main()
