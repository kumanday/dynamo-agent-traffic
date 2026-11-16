# Dynamo replay of Harness Leaderboard agent traffic

Every original trial of the public [Harness Leaderboard dataset](https://huggingface.co/buckets/joelniklaus/harness-leaderboard), 69,588 trials and 6,616,606 model calls, replayed through NVIDIA Dynamo's CPU simulator (`aisimulate predict --stack dynamo`) under four routers. The study was completed on 2026-11-14.

Report: https://kumanday.github.io/dynamo-agent-traffic/

The default KV router recomputes 3.1x the prompt tokens that session affinity does (25.5B against 8.3B). Setting `prefill_load_scale` to 16 recovers nearly all of it (8.7B).

## Headline numbers

All 216 leaderboard runs, 68,905 trials with a successful call, 6,616,606 requests per router:

| Router | Prefix reuse | Prefill tokens | Runs meeting SLA | Requests meeting SLA | Mean TTFT | Median run p99 TTFT |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Round-robin | 92.0% | 49.2B | 201 of 216 | 96.4% | 8.1 s | 1,008 ms |
| KV router, defaults | 95.8% | 25.5B | 194 of 216 | 98.0% | 186 ms | 762 ms |
| KV router, `prefill_load_scale` 16 | 98.6% | 8.7B | 215 of 216 | 99.9% | 83 ms | 353 ms |
| KV router with session affinity | 98.6% | 8.3B | 215 of 216 | 99.8% | 83 ms | 350 ms |

The 13 endpoint windows, which merge runs that loaded one provider endpoint at the same time:

| Router | Prefix reuse | Prefill tokens | Windows meeting SLA | Requests meeting SLA | Mean TTFT | Median window p99 TTFT |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Round-robin | 76.0% | 51.7B | 0 of 13 | 76.1% | 60.9 s | 697 s |
| KV router, defaults | 93.6% | 13.8B | 1 of 13 | 91.2% | 334 ms | 3.0 s |
| KV router, `prefill_load_scale` 16 | 98.4% | 3.4B | 13 of 13 | 99.8% | 98 ms | 473 ms |
| KV router with session affinity | 98.7% | 2.9B | 13 of 13 | 99.7% | 93 ms | 444 ms |

Prefill tokens are prompt tokens a worker had to compute because they were not in its KV cache. A replay meets the SLA when at least 99% of its requests get their first token within 2 s and stay within 50 ms between output tokens.

These are simulator results. Read the [limits](#limits) before using them.

## Where things are

| Path | Contents |
| --- | --- |
| [docs/index.html](docs/index.html) | The report page, served by GitHub Pages from `docs/`. Method, results, findings and limits, with stable section anchors. |
| [docs/data/](docs/data) | The JSON files the page draws its charts and tables from. |
| [docs/upstream-notes.md](docs/upstream-notes.md) | Technical notes for Dynamo and AISimulate maintainers. |
| [results/full/RESULTS.md](results/full/RESULTS.md) | Every table of the full replay. |
| [results/full/](results/full) | `units.csv` (one row per unit and router), the aggregates as JSON, and every replay's summary and configuration. |
| [results/pilot/](results/pilot) | The 39 pilot replays, the provider cache tables and the endpoint timeline. |
| [results/README.md](results/README.md) | What each results file holds, and the `units.csv` columns. |
| [scripts/](scripts) | The pipeline. |

To read the page locally, serve `docs/` over HTTP. It loads its data with relative fetches, which a `file://` URL blocks:

```sh
python3 -m http.server --directory docs
```

## How the pipeline runs

The scripts read an archived mirror of the public bucket, kept in a Cloud Storage bucket in the layout `scripts/delta_ingest.py` writes: `source-manifest.tar.zst`, then `archive/shard-NNNNN.tar.zst` files whose members are `raw/<path in the public bucket>`, plus a shard ledger. The mirror has two parts. The base archive is a first snapshot of the bucket. The delta archive holds the objects published after it, which `delta_ingest.py` finds by listing the bucket again and keeping objects whose path and Xet hash are missing from the base manifest. The script that wrote the base archive is not in this repository; it produced the same layout.

These are the scripts the study ran, with storage locations moved into environment variables and arguments, and names that pointed at private infrastructure replaced. They have not been run again since that edit. Each one compiles (`python3 -m py_compile`), and `build_report_data.py`, which is new, was run to build `docs/data/`.

| Variable | Used by | Meaning |
| --- | --- | --- |
| `HLB_ARCHIVE_BUCKET` | ingest, catalog, extraction | Cloud Storage bucket that holds the mirror. |
| `HLB_BASE_PREFIX` | catalog, `extract_full.py` | Object prefix of the base archive. Default `base/`. |
| `HLB_DELTA_PREFIX` | ingest, catalog, extraction | Object prefix of the delta archive. Default `delta/`. |
| `HLB_BASE_MANIFEST` | `delta_ingest.py` | Object key of the base archive's `source-manifest.tar.zst`. |
| `HLB_DELTA_ROOT` | ingest, catalog, `extract_full.py` | Local working directory of the ingest, with `manifest/`, `ack/`, `catalog/` and `ref/`. |
| `FULL_ROOT` | `extract_full.py`, `make_windows.py`, `make_chunks.py`, `run_full.py`, `aggregate_full.py` | Working directory of the full replay. Default `full`. |

Python needs `zstandard`, `google-cloud-storage`, `pyyaml` and, for the ingest, `huggingface_hub[hf_xet]`. The replays need Dynamo and AISimulate, which `scripts/sim/build.sh` builds from source. The study ran Dynamo `3e84909a` (ai-dynamo 1.7.0) with the AISimulate release it pins, `0.13.0.dev202610290000000087`.

Full-dataset replay:

```sh
python3 scripts/delta_ingest.py ingest --workers 8     # mirror objects published after the base snapshot
python3 scripts/catalog.py                             # catalog the delta; mark original executions
python3 scripts/extract_full.py index                  # one row per trial directory, originals marked
python3 scripts/extract_full.py extract --workers 40   # meter logs of every original trial, per run
python3 scripts/make_windows.py                        # merge runs that overlapped on one endpoint
python3 scripts/make_chunks.py 6 RUN_ID ...            # split long runs into six consecutive slices
python3 scripts/run_full.py                            # convert each unit, replay it under the four routers
python3 scripts/aggregate_full.py --out results/full   # RESULTS.md, units.csv, aggregate.json
python3 scripts/build_report_data.py                   # docs/data/*.json for the page
```

- `run_full.py` calls `hlb_to_agentic.py` to convert each unit to an agentic Mooncake v2 trace, sizes the pool at max(4, ceil(peak concurrent trials / 50)) workers, and runs `aisimulate predict --stack dynamo` on `scripts/sim/glm-b300-op.yaml` once per router. It replays every unit it finds, or the ones `--only` and `--exclude` select. `make_windows.py` writes all 33 overlapping groups; the study replayed 13 of them.
- The native DeepSeek-V4.1-Flash cross-check is a unit whose name starts with `dsvcheck-`, replayed on a DeepSeek-V4.1-Flash configuration. That configuration, as run, is in `results/full/replay-summaries.tgz`.
- `extract_full.py index` expects the base archive's manifest at `$FULL_ROOT/base-source-manifest.tar.zst`, and `ref/base-archive-ledger.json` and `ref/sealed-tasks.json` under `$HLB_DELTA_ROOT`. `sealed-tasks.json` lists 22 tasks that a separate analysis kept unopened while the pilot ran. The pilot skips them and the full replay includes them.

Pilot:

```sh
python3 scripts/extract_meters.py --workers 40                                   # original trials among the later objects
python3 scripts/hlb_to_agentic.py meters/RUN.jsonl.gz traces/RUN.upper.jsonl --hashes upper
python3 scripts/hlb_to_agentic.py meters/RUN.jsonl.gz /dev/null --stats-only     # statistics sidecar only
scripts/sim/sweep.sh NAME TRACE WORKERS POLICY                                   # one replay
python3 scripts/summarize_sweep.py sweep --json results/pilot/sweep-summary.json
python3 scripts/provider_gap.py results/pilot/conversion-stats
python3 scripts/endpoint_timeline.py meters --endpoint SUBSTRING
```

`scripts/sim/dynamo-engine-model-controls.patch` is not needed for these results. It lets `--stack dynamo` accept quantization and kernel selectors; see the notes for maintainers.

## Limits

- **The timing is modelled.** AISimulate rates agentic replay as functional only. Latencies come from its operator-level model on measured B300 kernel data. No request ran on a GPU.
- **Three of the four models are projected onto GLM-5.3-Flash.** Every run replays on GLM-5.3-Flash FP8, vLLM 0.31.0, two B300 GPUs per worker. DeepSeek-V4.1-Flash, flint and Ripple-65B-Preview traffic keeps its recorded token counts and takes GLM-5.3-Flash's timing. One DeepSeek run was also replayed natively as a cross-check.
- **Each run has one pool size.** The routers are compared on the same GPUs, so the results show recomputed tokens and SLA attainment at a fixed size. GPU count was varied only on the two pilot runs.
- **Prompt blocks are synthesized.** The converter reads no prompt text. Blocks are rebuilt from token counts on the assumption that a context grows by appending, and each call's output counts as new prefill in the next call.
- **Pacing is closed-loop.** Each agent waits for its simulated completions and keeps its recorded tool gaps.
- **Endpoint windows overlap the per-run results.** Their trials appear in both, so the two tables cannot be added. 13 of 33 overlapping groups were replayed.

## Data and credits

Study by [Kumanday Intelligence](https://github.com/kumanday).

The traffic comes from the [Harness Leaderboard dataset](https://huggingface.co/buckets/joelniklaus/harness-leaderboard) (`joelniklaus/harness-leaderboard`), which Joel Niklaus publishes with the [Harness Leaderboard](https://huggingface.co/spaces/joelniklaus/harness-leaderboard). The replay traces were built from each trial's per-call meter log and configuration. This repository holds aggregates derived from them: no meter logs, no per-call records and no prompt text. As of 2026-11-16 the bucket page states no licence, and the leaderboard's Space repository is tagged Apache-2.0.

The simulator is NVIDIA's [Dynamo](https://github.com/ai-dynamo/dynamo) with [AISimulate](https://github.com/ai-dynamo/aisimulate).

To cite: Kumanday Intelligence. "Dynamo replay of Harness Leaderboard agent traffic." Study completed 2026-11-14. https://kumanday.github.io/dynamo-agent-traffic/
