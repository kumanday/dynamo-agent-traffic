# Dynamo replay of Harness Leaderboard agent traffic

Every original trial of the public [Harness Leaderboard dataset](https://huggingface.co/buckets/joelniklaus/harness-leaderboard) as listed on 2026-11-20, 70,138 trials and 6,947,585 model calls, replayed through NVIDIA Dynamo's CPU simulator (`aisimulate predict --stack dynamo`) under four routers. Published 2026-11-20 by the Adaptive Systems Research Institute.

Report: https://adaptivesystems.institute/publications/dynamo-agent-traffic/

The default KV router recomputes 3.0x the prompt tokens that session affinity does (26.6B against 8.9B). Setting `prefill_load_scale` to 16 recovers nearly all of it (9.2B).

## Headline numbers

All 240 leaderboard runs, 69,923 trials with a successful call, 6,947,564 requests per router:

| Router | Prefix reuse | Prefill tokens | Runs meeting SLA | Requests meeting SLA | Mean TTFT | Median run p99 TTFT |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Round-robin | 92.7% | 47.8B | 220 of 240 | 96.8% | 6.3 s | 1,044 ms |
| KV router, defaults | 95.9% | 26.6B | 211 of 240 | 98.3% | 183 ms | 833 ms |
| KV router, `prefill_load_scale` 16 | 98.6% | 9.2B | 240 of 240 | 99.9% | 83 ms | 378 ms |
| KV router with session affinity | 98.6% | 8.9B | 240 of 240 | 99.9% | 83 ms | 381 ms |

The 16 endpoint windows, which merge runs that loaded one provider endpoint at the same time:

| Router | Prefix reuse | Prefill tokens | Windows meeting SLA | Requests meeting SLA | Mean TTFT | Median window p99 TTFT |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Round-robin | 77.2% | 43.8B | 3 of 16 | 76.7% | 53.6 s | 599 s |
| KV router, defaults | 93.5% | 12.5B | 4 of 16 | 90.3% | 347 ms | 2.6 s |
| KV router, `prefill_load_scale` 16 | 98.4% | 3.0B | 16 of 16 | 99.9% | 98 ms | 500 ms |
| KV router with session affinity | 98.7% | 2.5B | 16 of 16 | 99.8% | 92 ms | 440 ms |

Prefill tokens are prompt tokens a worker had to compute because they were not in its KV cache. A replay meets the SLA when at least 99% of its requests get their first token within 2 s and stay within 50 ms between output tokens.

These are simulator results. Read the [limits](#limits) before using them.

## Where things are

| Path | Contents |
| --- | --- |
| [report/index.html](report/index.html) | The report page, published at [adaptivesystems.institute](https://adaptivesystems.institute/publications/dynamo-agent-traffic/). Method, results, findings and limits, with stable section anchors. |
| [report/data/](report/data) | The JSON files the page draws its charts and tables from. |
| [report/assets/](report/assets) | The page's stylesheet and the script that draws its charts and tables. |
| [docs/upstream-notes.md](docs/upstream-notes.md) | Technical notes for Dynamo and AISimulate maintainers. |
| [results/full/RESULTS.md](results/full/RESULTS.md) | Every table of the full replay. |
| [results/full/](results/full) | `units.csv` (one row per unit and router), the aggregates as JSON, the provider cache tables, the endpoint timeline, and every replay's summary and configuration. |
| [results/pilot/](results/pilot) | The 39 pilot replays, with the provider cache tables and endpoint timeline of the pilot extraction. |
| [results/README.md](results/README.md) | What each results file holds, and the `units.csv` columns. |
| [scripts/](scripts) | The pipeline. |

To read the page locally, serve `report/` over HTTP. It loads its data with relative fetches, which a `file://` URL blocks:

```sh
python3 -m http.server --directory report
```

`scripts/check_report_numbers.py` compares the numbers on the rendered page with `results/full/RESULTS.md`. Its docstring has the two commands that dump the rendered page for it.

## Upstream

The four observations in [docs/upstream-notes.md](docs/upstream-notes.md) go to the Dynamo and AISimulate projects as issues and one pull request. This table carries the link to each once it is filed.

<!-- Replace "not yet filed" with the issue or pull request URL. -->

| Observation | Project | Issue or pull request |
| --- | --- | --- |
| 1. The replay runner rejects engine model controls | [ai-dynamo/dynamo](https://github.com/ai-dynamo/dynamo) | not yet filed |
| 2. The KV router gives up cached prefixes on long-context agent traffic | [ai-dynamo/dynamo](https://github.com/ai-dynamo/dynamo) | not yet filed |
| 3. Harness Leaderboard meter logs as an agentic trace source | [ai-dynamo/aisim](https://github.com/ai-dynamo/aisim) | not yet filed |
| 4. CLI supervisor cost and orphaned execution processes | [ai-dynamo/aisim](https://github.com/ai-dynamo/aisim) | not yet filed |

## How the pipeline runs

The pipeline reads the public bucket directly. `PREVIOUS` is an earlier pass's working directory, whose replays are reused for units whose original trials did not change; pass `-` (or a path that does not exist, for `OLD_ROOT`) to replay everything.

```sh
python3 scripts/list_bucket.py work                                        # trial folders and meter-log hashes of every run
python3 scripts/index_bucket.py work/listing PREVIOUS/index.jsonl.gz work/index   # original executions, per-run diff
python3 scripts/fetch_meters.py work/index work/listing work/fetched       # meter log and config of each new original
python3 scripts/assemble_meters.py PREVIOUS full work/index work/fetched   # full/meters/<run>.jsonl.gz
python3 scripts/make_windows.py                                            # merge runs that overlapped on one endpoint
python3 scripts/window_table.py full PREVIOUS > refresh/window-table.json  # peaks and spans of every window
cp -r work/index refresh/
OLD_ROOT=PREVIOUS REFRESH_DIR=refresh python3 scripts/prepare_refresh.py select   # choose windows, reuse unchanged replays
python3 scripts/run_full.py --convert-only                                 # agentic Mooncake v2 trace per unit
OLD_ROOT=PREVIOUS REFRESH_DIR=refresh python3 scripts/prepare_refresh.py plan     # slice long runs
python3 scripts/run_full.py --convert-only                                 # convert the slices
python3 scripts/run_full.py                                                # replay every unit under the four routers
python3 scripts/aggregate_full.py --out results/full                       # RESULTS.md, units.csv, aggregate.json
python3 scripts/provider_gap.py RUN_STATS > results/full/provider-cache-gap.md       # RUN_STATS: the runs' .stats.json only
python3 scripts/provider_gap.py RUN_STATS --by-run > results/full/provider-cache-gap-by-run.md
python3 scripts/endpoint_timeline.py full/meters --endpoint flint --endpoint Ripple > results/full/endpoint-timeline.md
python3 scripts/build_report_data.py                                       # report/data/*.json for the page
```

- `list_bucket.py` lists each run folder and its benchmark folders one level deep, then asks the bucket's paths-info endpoint for each trial's `agent/hlb-meter.jsonl`, `config.json` and, where the meter log is missing or under 256 bytes, `agent/trajectory.json`. That takes a few requests per run instead of a walk over every object. Anonymous requests are limited to 500 per five minutes per IP address.
- `index_bucket.py` applies the identity rule (the Xet hash of the meter log, or of the trajectory when the meter log is missing or under 256 bytes; the first trial by run ID and path holding an identity is the original) to the whole listing at once.
- `prepare_refresh.py select` replays a window when its merged peak is at least 1.5 times the busiest member run's peak, the merged peak is at least 60 trials and the window spans at most 36 hours, and replays every flint window. `prepare_refresh.py plan` predicts each replay at 90 seconds per simulated hour plus 90 seconds per million output tokens (fitted on the first pass) and splits a run predicted above 40 minutes into consecutive trial slices of about 30 minutes, at most 12. `aggregate_full.py` recombines the slices.
- `run_full.py` calls `hlb_to_agentic.py` to convert each unit, sizes the pool at max(4, ceil(peak concurrent trials / 50)) workers, and runs `aisimulate predict --stack dynamo` on `scripts/sim/glm-b300-op.yaml` once per router. It replays every unit under `$FULL_ROOT/meters` and `$FULL_ROOT/units`, or the ones `--only` and `--exclude` select.
- `provider_gap.py` tabulates each provider's cached share against the append-only reusable prefix. Give it a directory holding only the runs' `.stats.json` files from `full/traces`: windows, slices and the native cross-check repeat the runs' trials.
- The native DeepSeek-V4.1-Flash cross-check is a unit whose name starts with `dsvcheck-`, replayed on a DeepSeek-V4.1-Flash configuration. That configuration, as run, is in `results/full/replay-summaries.tgz`.

Python needs `pyyaml` and `huggingface_hub[hf_xet]`. The replays need Dynamo and AISimulate, which `scripts/sim/build.sh` builds from source. The study ran Dynamo `3e84909a` (ai-dynamo 1.7.0) with the AISimulate release it pins, `0.13.0.dev202610290000000087`.

The first pass read an archived mirror of the bucket instead of the bucket itself, through `delta_ingest.py`, `catalog.py` and `extract_full.py`. Those scripts are kept here because units reused from that pass came through them; the identity rule is the same, and the meter logs are identical by hash.

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

- **The timing is modeled.** AISimulate rates agentic replay as functional only. Latencies come from its operator-level model on measured B300 kernel data. No request ran on a GPU.
- **Four of the five models are projected onto GLM-5.3-Flash.** Every run replays on GLM-5.3-Flash FP8, vLLM 0.31.0, two B300 GPUs per worker. DeepSeek-V4.1-Flash, flint, Inkling-2-Small and Ripple-65B-Preview traffic keeps its recorded token counts and takes GLM-5.3-Flash's timing. One DeepSeek run was also replayed natively as a cross-check.
- **Each run has one pool size.** The routers are compared on the same GPUs, so the results show recomputed tokens and SLA attainment at a fixed size. GPU count was varied only on the two pilot runs.
- **Prompt blocks are synthesized.** The converter reads no prompt text. Blocks are rebuilt from token counts on the assumption that a context grows by appending, and each call's output counts as new prefill in the next call.
- **Pacing is closed-loop.** Each agent waits for its simulated completions and keeps its recorded tool gaps.
- **Endpoint windows overlap the per-run results.** Their trials appear in both, so the two tables cannot be added. 16 of 43 overlapping groups were replayed.

## Data and credits

Study by [Leonardo Gonzalez](https://github.com/kumanday).

The traffic comes from the [Harness Leaderboard dataset](https://huggingface.co/buckets/joelniklaus/harness-leaderboard) (`joelniklaus/harness-leaderboard`), which Joel Niklaus publishes with the [Harness Leaderboard](https://huggingface.co/spaces/joelniklaus/harness-leaderboard) under the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0). The study used every run in the bucket as listed between 01:06 and 01:23 UTC on 2026-11-21, the evening of 2026-11-20 in US time. The replay traces were built from each trial's per-call meter log and configuration. This repository holds aggregates derived from them: no meter logs, no per-call records and no prompt text.

The code, tables and page in this repository are under the [MIT License](LICENSE). The dataset stays under the Apache License 2.0.

The simulator is NVIDIA's [Dynamo](https://github.com/ai-dynamo/dynamo) with [AISimulate](https://github.com/ai-dynamo/aisim), whose repository was renamed from `ai-dynamo/aisimulate` after the study ran.

To cite, use [CITATION.cff](CITATION.cff) (GitHub's "Cite this repository" button reads it): Leonardo Gonzalez. "Dynamo replay of Harness Leaderboard agent traffic." Adaptive Systems Research Institute, 2026-11-20. https://adaptivesystems.institute/publications/dynamo-agent-traffic/
