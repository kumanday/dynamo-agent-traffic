# Results

Aggregates only. Nothing here holds a meter log, a per-call record or prompt text.

Router codes: `rr` round-robin, `kv` KV router with defaults, `kvp4` and `kvp16` KV router with `prefill_load_scale` 4 or 16, `aff` KV router with session affinity (TTL 300 s).

## full/

The full-dataset replay: 240 runs, 16 endpoint windows and one native DeepSeek-V4.1-Flash cross-check, each under four routers.

| File | Contents |
| --- | --- |
| `RESULTS.md` | Every table: all runs, each traffic source, each harness, the slice check, the endpoint windows and the native cross-check. Written by `scripts/aggregate_full.py`. |
| `units.csv` | One row per unit and router. Columns below. |
| `aggregate.json` | The totals behind `RESULTS.md`, by scope, with the list of units in each. |
| `windows.json` | All 43 groups of runs that overlapped on one endpoint. The 16 that were replayed are the `window` rows of `units.csv`. |
| `slice-check.json` | Full against six-slice replays for the three runs that have both. |
| `unit-stats.json` | Conversion statistics per unit: trials, requests, peak concurrent trials, token totals, provider cached share, reuse bounds, stream counts. |
| `index-summary.json` | The bucket listing (start and end time, size and file count) and, over it, trial directories, original executions, copies and trials without an identity. `runStatus` counts runs whose originals are new, unchanged, changed or removed against the 2026-11-12 pass. |
| `assemble-summary.json` | Runs, original trials and calls in the meter files. `bySource` splits the trials into those taken from the 2026-11-12 pass (`previous`) and those read from the bucket (`fetched`). `calls` counts every logged model call; 6,947,564 of them returned successfully with a non-empty prompt and are replayed. |
| `provider-cache-gap.md`, `provider-cache-gap-by-run.md` | Provider cached share against the append-only reusable prefix, by harness, model and provider, over all original trials. Written by `scripts/provider_gap.py`. |
| `endpoint-timeline.md` | Provider cached share and active trials in 30-minute buckets for the flint and Ripple-65B-Preview endpoints, over all original trials. Written by `scripts/endpoint_timeline.py`. |
| `replay-summaries.tgz` | `results/<unit>/<router>/config.yaml` for every replay and `summary.json` for every replay, including the 94 slice units (`chunk-<run>-cNN`). Trace paths are relative. |

`units.csv` columns:

| Column | Meaning |
| --- | --- |
| `unit`, `kind` | Run ID or window name; `run`, `window` or `dsvcheck` (the native cross-check). |
| `policy` | Router code. |
| `family`, `harness` | Traffic source, and the harness version that made most of the unit's calls. |
| `plays`, `requests`, `peakTrials` | Trials with a successful call, successful calls, peak concurrent trials. |
| `workers`, `gpus` | Simulated pool. |
| `inputTokens`, `providerCachedRatio`, `traceReuseRatio` | Prompt tokens, the share the real provider served from cache, and the share the replay trace allows a perfect cache to reuse. |
| `prefixReuse`, `prefillTokens` | Simulated share of prompt tokens served from KV cache, and prompt tokens computed. |
| `ttftMean`, `ttftP99`, `itlMean`, `itlP99` | Milliseconds. |
| `goodput`, `goodputShare`, `completed` | Requests meeting 2 s TTFT and 50 ms ITL, their share, and completed requests. A unit meets the SLA at a share of 0.99 or more. |
| `trialP50Min`, `trialP90Min` | Simulated trial duration in minutes. |
| `gpuHours`, `wallSeconds` | Simulated GPU-hours, and the wall time of the replay itself. |
| `replayedAs` | `full`, or `N slices` for a run recombined from N slices. |

`sealedTrials` in `assemble-summary.json` counts trials on 22 tasks that a separate analysis kept unopened while the pilot ran. The full replay includes them.

## pilot/

The work that preceded the full replay, on runs published after the first snapshot and outside those 22 tasks.

| File | Contents |
| --- | --- |
| `sweep-summary.md`, `sweep-summary.json` | The 39 pilot replays: two runs and their first 100 trials, at 4 to 32 workers. Written by `scripts/summarize_sweep.py`. |
| `sweep-summaries.json` | Each pilot replay's full simulator summary and configuration. |
| `provider-cache-gap.md`, `provider-cache-gap-by-run.md` | Provider cached share against the append-only reusable prefix, by harness, model and provider. Written by `scripts/provider_gap.py`. |
| `endpoint-timeline.md` | Provider cached share and active trials in 30-minute buckets for the flint and Ripple-65B-Preview endpoints. Written by `scripts/endpoint_timeline.py`. |
| `conversion-stats/` | Conversion statistics for the 119 pilot runs, with lower-bound hashes. |
| `smoke20-summary.json` | Summary of a 20-trial smoke replay on four workers (2,428 requests). |

Trace names in the pilot files: `flint-hermes-upper` and `glm-openclaw-upper` are the two full runs with upper-bound hashes, `glm-openclaw-lower` is the OpenClaw run with lower-bound hashes, and `calib-hermes100` and `calib-glm100` are the first 100 trials of each.
