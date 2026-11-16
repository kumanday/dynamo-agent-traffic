"""Resumable acquisition of Harness Leaderboard objects published after a first snapshot of the bucket.

The first snapshot (the base archive) was mirrored earlier into the same layout. Its frozen manifest
lists every object it holds.
- The inventory lists every bucket prefix and keeps only objects whose (path, xetHash) is absent from
  the base manifest, so late trials in already-mirrored runs are captured with new runs.
- The core phase carries agent/hlb-meter.jsonl, so per-call serving telemetry lands first.
- Core shards carry raw objects only.
- Uploads use the ambient Cloud Storage credentials with if-generation-match=0.

Archive layout under the delta prefix: source-manifest.tar.zst, archive/shard-NNNNN.tar.zst with
raw/<source path> members and one receipts member, phase summaries, archive-ledger.json and
full-run-summary-final.json.

Locations come from the environment:
  HLB_ARCHIVE_BUCKET   Cloud Storage bucket that holds the mirror (required)
  HLB_DELTA_PREFIX     object prefix this script writes under (default "delta/")
  HLB_BASE_MANIFEST    object key of the base archive's source-manifest.tar.zst
                       (default "base/source-manifest.tar.zst")
  HLB_DELTA_ROOT       local working directory (default: the directory of this script)
  HLB_RECEIPTS_MEMBER  name of the receipts member inside each shard
"""
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path, PurePosixPath
from collections import Counter
from io import BytesIO
from urllib.request import urlopen
import argparse, hashlib, json, os, tarfile, tempfile, time
import zstandard
from google.cloud import storage
from huggingface_hub import BucketFile, BucketFolder, download_bucket_files, list_bucket_tree
from huggingface_hub.errors import HfHubHTTPError

BUCKET = "joelniklaus/harness-leaderboard"
GCS_BUCKET = os.environ.get("HLB_ARCHIVE_BUCKET", "")
GCS_PREFIX = os.environ.get("HLB_DELTA_PREFIX", "delta/")
FROZEN_MANIFEST = os.environ.get("HLB_BASE_MANIFEST", "base/source-manifest.tar.zst")
RECEIPTS = os.environ.get("HLB_RECEIPTS_MEMBER", "__mirror/object-receipts.jsonl")
ROOT = Path(os.environ.get("HLB_DELTA_ROOT") or Path(__file__).resolve().parent)
PLAN = ROOT / "manifest"
ACKS = ROOT / "ack"
OBJECT_CAP = 4_000_000
BYTE_CAP = 700_000_000_000
MAX_BATCH_OBJECTS = 1400
MAX_BATCH_BYTES = 256 * 2**20
gcs = None


def encoded(value):
    return (json.dumps(value, ensure_ascii=True, separators=(",", ":")) + "\n").encode()


def atomic(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(encoded(value))
    os.replace(temp, path)


def safe(path):
    p = PurePosixPath(path)
    return not p.is_absolute() and p.as_posix() == path and all(x not in (".", "..") for x in p.parts) and "\\" not in path


def file_row(o):
    return dict(type="file", path=o.path, size=o.size, xetHash=o.xet_hash)


def trial_of(p):
    return "/".join(p.split("/")[:4])


def bucket():
    global gcs
    if gcs is None:
        gcs = storage.Client().bucket(GCS_BUCKET)
    return gcs


def init_worker():
    # A client created in the parent must not be shared across forked workers.
    global gcs
    gcs = None


def frozen_identities():
    """(path, xetHash) pairs from the base archive's frozen manifest."""
    cache = ROOT / "frozen-identities.txt"
    if not cache.exists():
        seen = set()
        with tempfile.TemporaryDirectory(dir=ROOT / "stage") as tmp:
            local = Path(tmp) / "source-manifest.tar.zst"
            bucket().blob(FROZEN_MANIFEST).download_to_filename(str(local))
            with local.open("rb") as f, zstandard.ZstdDecompressor().stream_reader(f) as stream:
                with tarfile.open(fileobj=stream, mode="r|") as tar:
                    for member in tar:
                        if not member.isfile() or not member.name.endswith(".jsonl"):
                            continue
                        for line in tar.extractfile(member):
                            row = json.loads(line)
                            seen.add(f'{row["path"]}\t{row.get("xetHash")}')
        temp = cache.with_suffix(".tmp")
        temp.write_text("\n".join(sorted(seen)) + "\n")
        os.replace(temp, cache)
    return set(cache.read_text().splitlines())


RETRYABLE = (429, 500, 502, 503, 504)


def write_prefix(entry, frozen):
    """List one prefix. A per-prefix receipt makes the inventory resumable across restarts."""
    i, prefix = entry
    path = PLAN / f"{i:04d}.jsonl"
    done = PLAN / f"{i:04d}.done.json"
    if done.exists():
        return json.loads(done.read_text())
    temp = path.with_suffix(".tmp")
    for attempt in range(12):
        listed = count = volume = 0
        try:
            with temp.open("wb") as f:
                for item in list_bucket_tree(BUCKET, prefix=prefix, recursive=True, token=False):
                    if not isinstance(item, BucketFile):
                        continue
                    row = file_row(item)
                    assert safe(row["path"]) and row["size"] >= 0
                    if not row["path"].startswith(prefix + "/"):
                        raise RuntimeError("object outside manifest prefix")
                    listed += 1
                    if f'{row["path"]}\t{row["xetHash"]}' in frozen:
                        continue
                    f.write(encoded(row)); count += 1; volume += row["size"]
            break
        except HfHubHTTPError as error:
            status = getattr(getattr(error, "response", None), "status_code", None)
            if status not in RETRYABLE or attempt == 11:
                raise
            wait_s = min(900, 60 * 2 ** min(attempt, 4))
            print("LIST_RETRY", json.dumps(dict(prefix=prefix, status=status, attempt=attempt, waitSeconds=wait_s)), flush=True)
            time.sleep(wait_s)
    os.replace(temp, path)
    with path.open("rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    value = dict(prefix=prefix, path=path.name, listed=listed, objects=count, bytes=volume, sha256=digest,
                 listedAt=time.time())
    atomic(done, value)
    print("LISTED", json.dumps({k: value[k] for k in ("prefix", "listed", "objects", "bytes")}), flush=True)
    return value


def inventory(list_workers=4):
    PLAN.mkdir(exist_ok=True)
    receipt = PLAN / "frozen.json"
    if receipt.exists():
        return json.loads(receipt.read_text())
    frozen = frozen_identities()
    plan = PLAN / "prefixes.json"
    if not plan.exists():
        # Freeze the prefix list once. The bucket is live, so a later listing could renumber prefixes.
        started = time.time()
        with urlopen("https://huggingface.co/api/buckets/" + BUCKET, timeout=15) as response:
            info = json.load(response)
        root = list(list_bucket_tree(BUCKET, recursive=False, token=False))
        run = list(list_bucket_tree(BUCKET, prefix="runs", recursive=False, token=False))
        prefixes = sorted({*[x.path for x in root if isinstance(x, BucketFolder) and x.path != "runs"],
                           *[x.path for x in run if isinstance(x, BucketFolder)]})
        entries = [file_row(x) for x in [*root, *run] if isinstance(x, BucketFile)]
        direct = [r for r in entries if f'{r["path"]}\t{r["xetHash"]}' not in frozen]
        with (PLAN / "direct.jsonl").open("wb") as f:
            for r in direct:
                f.write(encoded(r))
        with (PLAN / "direct.jsonl").open("rb") as f:
            first = dict(prefix="", path="direct.jsonl", listed=len(entries), objects=len(direct),
                         bytes=sum(r["size"] for r in direct), sha256=hashlib.file_digest(f, "sha256").hexdigest())
        atomic(plan, dict(listingStarted=started, bucketObserved={k: info[k] for k in ("updatedAt", "size", "totalFiles")},
                          prefixes=prefixes, direct=first))
    p = json.loads(plan.read_text())
    frozen_prefixes = {"/".join(x.split("\t", 1)[0].split("/")[:2]) for x in frozen}
    work = list(enumerate(p["prefixes"]))
    # New runs first, so the data that matters most is listed before the late-object sweep of runs already in the base archive.
    work.sort(key=lambda e: (e[1] in frozen_prefixes, e[0]))
    with ThreadPoolExecutor(max_workers=list_workers) as pool:
        listed = {e[0]: v for e, v in zip(work, pool.map(lambda e: write_prefix(e, frozen), work))}
    files = [p["direct"], *[listed[i] for i in range(len(p["prefixes"]))]]
    counts = dict(objects=sum(x["objects"] for x in files), bytes=sum(x["bytes"] for x in files),
                  listed=sum(x["listed"] for x in files))
    if counts["objects"] > OBJECT_CAP or counts["bytes"] > BYTE_CAP:
        raise SystemExit("Delta manifest exceeds the object or byte cap")
    value = dict(schema="hlb-delta-manifest/v1", base="gs://" + GCS_BUCKET + "/" + FROZEN_MANIFEST,
                 listingStarted=p["listingStarted"], created=time.time(), bucket=BUCKET, shards=files,
                 bucketObserved=p["bucketObserved"], **counts)
    atomic(receipt, value)
    print("FROZEN", json.dumps(counts), flush=True)
    return value


def core(p):
    parts = p.split("/")
    if p == "index/public.json":
        return True
    if parts[0] != "runs":
        return False
    if len(parts) <= 4 and (parts[-1] in {"run.json", "plan.json", "invalid.json", "dispatch.json"} or
                            parts[-1].startswith("trials-") and parts[-1].endswith(".jsonl")):
        return True
    return len(parts) >= 5 and "/".join(parts[4:]) in {
        "agent/trajectory.json", "result.json", "config.json", "lock.json", "agent/hlb-meter.jsonl"}


def groups(receipt, is_core):
    for shard in receipt["shards"]:
        current = []; size = 0; last = None
        with (PLAN / shard["path"]).open() as f:
            for line in f:
                row = json.loads(line); p = row["path"]
                if core(p) != is_core:
                    continue
                trial = trial_of(p)
                over = len(current) >= MAX_BATCH_OBJECTS or size + row["size"] > MAX_BATCH_BYTES
                if current and over and (not is_core or trial != last):
                    yield current
                    current = []; size = 0
                current.append(row); size += row["size"]; last = trial
        if current:
            yield current


def put(path, key):
    blob = bucket().blob(GCS_PREFIX + key)
    for attempt in range(4):
        try:
            blob.upload_from_filename(str(path), if_generation_match=0, checksum="md5", timeout=600)
            blob.reload()
            return dict(generation=str(blob.generation), md5=blob.md5_hash)
        except Exception as error:
            if "412" in str(error) or "conditionNotMet" in str(error):
                blob.reload()
                return dict(generation=str(blob.generation), md5=blob.md5_hash, existing=True)
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


class HashReader:
    def __init__(self, source):
        self.source = source
        self.sha = hashlib.sha256()

    def read(self, n=-1):
        data = self.source.read(n); self.sha.update(data); return data


def add_file(tar, local, name):
    info = tarfile.TarInfo(name)
    info.mode = 0o600; info.size = local.stat().st_size
    with local.open("rb") as f:
        source = HashReader(f); tar.addfile(info, source)
    return source.sha.hexdigest()


def add_bytes(tar, data, name):
    info = tarfile.TarInfo(name)
    info.mode = 0o600; info.size = len(data)
    tar.addfile(info, BytesIO(data))


def fetch(batch, scratch):
    pairs = [(BucketFile(**row), scratch / str(i)) for i, row in enumerate(batch)]
    remaining = pairs
    for attempt in range(3):
        try:
            download_bucket_files(BUCKET, remaining, raise_on_missing_files=True, token=False)
        except Exception:
            if attempt < 2:
                time.sleep(2 ** attempt)
        remaining = []
        for item, file in pairs:
            if not file.exists():
                remaining.append((item, file))
            elif file.stat().st_size != item.size:
                file.unlink(); remaining.append((item, file))
        if not remaining:
            break
    missing = {item.path for item, _ in remaining}
    return {item.path: f for item, f in pairs if item.path not in missing}, missing


def run_shard(work):
    serial, phase, batch = work
    started = time.monotonic()
    ack = ACKS / f"{serial:05d}.json"
    key = f"archive/shard-{serial:05d}.tar.zst"
    manifest_digest = hashlib.sha256(b"".join(encoded(x) for x in batch)).hexdigest()
    if ack.exists():
        state = json.loads(ack.read_text())
        assert state["manifestDigest"] == manifest_digest
        return state
    with tempfile.TemporaryDirectory(dir=ROOT / "stage", prefix=f"s{serial:05d}-") as temp:
        scratch = Path(temp)
        at = time.monotonic()
        by_path, missing = fetch(batch, scratch)
        download = time.monotonic() - at
        archive = scratch / "payload.tar.zst"
        with archive.open("wb") as output, zstandard.ZstdCompressor(level=1).stream_writer(output) as stream, \
                tarfile.open(fileobj=stream, mode="w|") as tar:
            receipts = []
            for row in batch:
                p = row["path"]
                if p in by_path:
                    digest = add_file(tar, by_path[p], "raw/" + p)
                    receipts.append(dict(path=p, sha256=digest, xetHash=row["xetHash"], bytes=row["size"], status="verified"))
                else:
                    receipts.append(dict(path=p, xetHash=row["xetHash"], bytes=row["size"], status="unavailable"))
            add_bytes(tar, b"".join(encoded(row) for row in receipts), RECEIPTS)
        identity = put(archive, key)
        state = dict(serial=serial, phase=phase, manifestDigest=manifest_digest,
                     objects=len(batch), verified=len(by_path), unavailable=len(missing),
                     bytes=sum(row["size"] for row in batch if row["path"] not in missing),
                     archiveBytes=archive.stat().st_size, archiveKey=key, projection={},
                     downloadSeconds=round(download, 3), wallSeconds=round(time.monotonic() - started, 3), **identity)
        atomic(ack, state)
        return state


def archive_manifest():
    if (ROOT / "manifest-uploaded.json").exists():
        return
    with tempfile.TemporaryDirectory(dir=ROOT / "stage") as tmp:
        target = Path(tmp) / "source-manifest.tar.zst"
        with target.open("wb") as output, zstandard.ZstdCompressor(level=1).stream_writer(output) as stream, \
                tarfile.open(fileobj=stream, mode="w|") as tar:
            for path in sorted(PLAN.glob("*.json*")):
                if not path.name.endswith(".tmp"):
                    add_file(tar, path, "manifest/" + path.name)
        atomic(ROOT / "manifest-uploaded.json", put(target, "source-manifest.tar.zst"))


def ledger():
    rows = [json.loads(p.read_text()) for p in sorted(ACKS.glob("*.json"))]
    out = ROOT / "archive-ledger.json"
    out.write_text(json.dumps(rows, indent=1))
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("inventory", "ingest"))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--list-workers", type=int, default=4)
    args = parser.parse_args()
    assert 1 <= args.workers <= 32 and 1 <= args.list_workers <= 12
    if not GCS_BUCKET:
        raise SystemExit("set HLB_ARCHIVE_BUCKET")
    for d in (PLAN, ACKS, ROOT / "stage"):
        d.mkdir(exist_ok=True)
    receipt = inventory(args.list_workers)
    if args.mode == "inventory":
        return
    archive_manifest()
    serial = 0
    start = time.monotonic()
    errors = []
    aggregate = Counter()
    with ProcessPoolExecutor(max_workers=args.workers, initializer=init_worker) as pool:
        for phase in ("core", "archive"):
            pending = {}
            phase_start = serial
            iterator = iter(groups(receipt, phase == "core"))

            def refill():
                nonlocal serial
                while len(pending) < args.workers * 2:
                    try:
                        batch = next(iterator)
                    except StopIteration:
                        return
                    pending[pool.submit(run_shard, (serial, phase, batch))] = serial
                    serial += 1
            refill()
            while pending:
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    part = pending.pop(future)
                    try:
                        row = future.result()
                        aggregate.update({k: row[k] for k in ("objects", "verified", "unavailable", "bytes", "archiveBytes")})
                        if part % 10 == 0:
                            print("PROGRESS", json.dumps({"phase": phase, "part": part,
                                  "elapsedSeconds": round(time.monotonic() - start), **aggregate}), flush=True)
                    except Exception as error:
                        errors.append(dict(shard=part, phase=phase, error=str(error)[:240]))
                        print("SHARD_ERROR", json.dumps(errors[-1]), flush=True)
                if len(errors) >= 10:
                    raise RuntimeError("Stopped after ten shard failures")
                refill()
            if serial == phase_start:
                raise RuntimeError(f"Delta manifest yielded no {phase} shards")
            summary = ROOT / (phase + "-complete.json")
            atomic(summary, dict(phase=phase, aggregate=aggregate, errors=errors, shards=serial))
            put(summary, summary.name)
            put(ledger(), f"archive-ledger.{phase}.json")
            print("PHASE_COMPLETE", phase, json.dumps(dict(errors=len(errors), shards=serial)), flush=True)
    report = dict(aggregate=aggregate, errors=errors, expected={"objects": receipt["objects"], "bytes": receipt["bytes"]},
                  elapsedSeconds=round(time.monotonic() - start),
                  archiveComplete=not errors and aggregate["objects"] == receipt["objects"] and not aggregate["unavailable"])
    out = ROOT / "full-run-summary-final.json"
    atomic(out, report)
    put(out, out.name)
    put(ledger(), "archive-ledger.json")
    print("FINISHED", json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
