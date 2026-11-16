# Full-dataset Dynamo replay

216 leaderboard runs, 68,905 trials, 6,616,606 requests per router. A replay meets the SLA when at least 99% of its requests meet 2 s TTFT and 50 ms inter-token latency.

1 run was replayed as consecutive trial slices and recombined: `20261025-161003-flint-full-default-5596`.

## All leaderboard runs

| Router | Prefix reuse | Prefill tokens | Runs meeting SLA | Requests meeting SLA | Mean TTFT | Median run p99 TTFT | Worst run p99 TTFT | Median trial p50 | GPU-hours |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Round-robin | 92.0% | 49.18B | 201 of 216 | 96.4% | 8,108 ms | 1,008 ms | 1,002.6 s | 13.5 min | 12,577 |
| KV router (defaults) | 95.8% | 25.53B | 194 of 216 | 98.0% | 186 ms | 762 ms | 6.3 s | 13.1 min | 12,085 |
| KV router, prefill_load_scale 16 | 98.6% | 8.74B | 215 of 216 | 99.9% | 83 ms | 353 ms | 2.8 s | 13.1 min | 12,077 |
| KV router + session affinity | 98.6% | 8.32B | 215 of 216 | 99.8% | 83 ms | 350 ms | 4.5 s | 12.9 min | 12,075 |

Prefill relative to affinity, per run (median / p90): Round-robin 3.72x / 3.90x; KV router (defaults) 1.46x / 3.17x; KV router, prefill_load_scale 16 1.00x / 1.07x.
Provider cached share over the same runs: 91.6%.

SLA outcomes per run (Y meets, n misses; order: round-robin, KV router, KV with prefill_load_scale 16, affinity): YYYY 191, nnYY 11, YnYY 10, nYYY 3, nnnn 1.

## Traffic from DeepSeek-V4.1-Flash

| Router | Prefix reuse | Prefill tokens | Runs meeting SLA | Requests meeting SLA | Mean TTFT | Median run p99 TTFT | Worst run p99 TTFT | Median trial p50 | GPU-hours |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Round-robin | 94.6% | 10.47B | 96 of 97 | 99.8% | 190 ms | 1,038 ms | 2.1 s | 13.1 min | 6,121 |
| KV router (defaults) | 95.9% | 7.93B | 89 of 97 | 99.4% | 166 ms | 775 ms | 2.9 s | 12.7 min | 6,111 |
| KV router, prefill_load_scale 16 | 98.5% | 2.91B | 97 of 97 | 100.0% | 82 ms | 350 ms | 1.3 s | 13.1 min | 6,116 |
| KV router + session affinity | 98.5% | 2.87B | 97 of 97 | 100.0% | 81 ms | 343 ms | 1.3 s | 12.8 min | 6,115 |

Prefill relative to affinity, per run (median / p90): Round-robin 3.74x / 3.88x; KV router (defaults) 1.36x / 3.06x; KV router, prefill_load_scale 16 1.00x / 1.03x.
Provider cached share over the same runs: 98.5%.

SLA outcomes per run (Y meets, n misses; order: round-robin, KV router, KV with prefill_load_scale 16, affinity): YYYY 88, YnYY 8, nYYY 1.

## Traffic from GLM-5.3-Flash (zai-org)

| Router | Prefix reuse | Prefill tokens | Runs meeting SLA | Requests meeting SLA | Mean TTFT | Median run p99 TTFT | Worst run p99 TTFT | Median trial p50 | GPU-hours |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Round-robin | 95.3% | 5.74B | 77 of 80 | 99.7% | 145 ms | 858 ms | 4.2 s | 10.7 min | 2,577 |
| KV router (defaults) | 96.0% | 4.97B | 76 of 80 | 99.6% | 142 ms | 559 ms | 2.1 s | 10.5 min | 2,573 |
| KV router, prefill_load_scale 16 | 98.5% | 1.80B | 80 of 80 | 100.0% | 75 ms | 332 ms | 1.3 s | 10.4 min | 2,573 |
| KV router + session affinity | 98.7% | 1.62B | 80 of 80 | 99.9% | 73 ms | 315 ms | 1.3 s | 10.4 min | 2,573 |

Prefill relative to affinity, per run (median / p90): Round-robin 3.64x / 3.90x; KV router (defaults) 1.28x / 3.09x; KV router, prefill_load_scale 16 1.00x / 1.07x.
Provider cached share over the same runs: 96.1%.

SLA outcomes per run (Y meets, n misses; order: round-robin, KV router, KV with prefill_load_scale 16, affinity): YYYY 75, YnYY 2, nnYY 2, nYYY 1.

## Traffic from Ripple-65B-Preview

| Router | Prefix reuse | Prefill tokens | Runs meeting SLA | Requests meeting SLA | Mean TTFT | Median run p99 TTFT | Worst run p99 TTFT | Median trial p50 | GPU-hours |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Round-robin | 90.0% | 14.18B | 12 of 16 | 94.1% | 15,456 ms | 1,336 ms | 1,002.6 s | 33.1 min | 1,590 |
| KV router (defaults) | 95.5% | 6.38B | 12 of 16 | 98.0% | 221 ms | 1,666 ms | 4.5 s | 32.3 min | 1,398 |
| KV router, prefill_load_scale 16 | 98.6% | 2.05B | 16 of 16 | 99.9% | 94 ms | 489 ms | 0.9 s | 29.0 min | 1,393 |
| KV router + session affinity | 98.6% | 2.00B | 16 of 16 | 99.8% | 94 ms | 420 ms | 0.8 s | 28.9 min | 1,392 |

Prefill relative to affinity, per run (median / p90): Round-robin 3.60x / 3.82x; KV router (defaults) 3.12x / 3.41x; KV router, prefill_load_scale 16 1.02x / 1.14x.
Provider cached share over the same runs: 97.2%.

SLA outcomes per run (Y meets, n misses; order: round-robin, KV router, KV with prefill_load_scale 16, affinity): YYYY 12, nnYY 4.

## Traffic from flint

| Router | Prefix reuse | Prefill tokens | Runs meeting SLA | Requests meeting SLA | Mean TTFT | Median run p99 TTFT | Worst run p99 TTFT | Median trial p50 | GPU-hours |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Round-robin | 87.6% | 18.78B | 16 of 23 | 90.0% | 21,299 ms | 1,165 ms | 950.9 s | 18.2 min | 2,289 |
| KV router (defaults) | 95.9% | 6.25B | 17 of 23 | 94.1% | 231 ms | 1,012 ms | 6.3 s | 18.2 min | 2,002 |
| KV router, prefill_load_scale 16 | 98.7% | 1.98B | 22 of 23 | 99.7% | 86 ms | 431 ms | 2.8 s | 17.6 min | 1,995 |
| KV router + session affinity | 98.8% | 1.84B | 22 of 23 | 99.7% | 86 ms | 404 ms | 4.5 s | 17.8 min | 1,995 |

Prefill relative to affinity, per run (median / p90): Round-robin 3.64x / 22.32x; KV router (defaults) 2.29x / 4.19x; KV router, prefill_load_scale 16 1.00x / 1.13x.
Provider cached share over the same runs: 73.8%.

SLA outcomes per run (Y meets, n misses; order: round-robin, KV router, KV with prefill_load_scale 16, affinity): YYYY 16, nnYY 5, nnnn 1, nYYY 1.

## By harness (prefill tokens, billions; runs meeting SLA)

| Harness | Runs | Requests | Round-robin | KV router | KV, prefill_load_scale 16 | Affinity |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| claude-code-bare@2.1.300 | 22 | 301,717 | 1.39 (22) | 1.10 (22) | 0.39 (22) | 0.38 (22) |
| claude-code@2.1.300 | 9 | 1,148,980 | 5.95 (9) | 4.88 (9) | 1.69 (9) | 1.71 (9) |
| codex-apply-patch@0.162.1 | 1 | 5,683 | 0.02 (1) | 0.01 (1) | 0.00 (1) | 0.00 (1) |
| codex@0.162.1 | 3 | 18,948 | 0.07 (3) | 0.05 (3) | 0.02 (3) | 0.02 (3) |
| deepseek-harness@0.2.2-rc.1 | 19 | 389,473 | 7.70 (16) | 1.71 (16) | 0.51 (19) | 0.47 (19) |
| fx@0.0.16 | 11 | 129,170 | 4.63 (10) | 0.68 (10) | 0.21 (11) | 0.18 (11) |
| grok-build@1.0.77 | 6 | 426,114 | 2.26 (4) | 1.78 (4) | 0.65 (6) | 0.63 (6) |
| hermes@v0.22.1 | 25 | 353,710 | 4.99 (23) | 2.41 (17) | 0.61 (25) | 0.61 (25) |
| kimi-code@2.2.0 | 19 | 214,950 | 1.12 (18) | 0.83 (18) | 0.31 (19) | 0.31 (19) |
| mini-swe-agent@2.4.6 | 9 | 366,285 | 2.15 (9) | 1.75 (9) | 0.61 (9) | 0.61 (9) |
| oh-my-pi@18.18.0 | 1 | 1,718 | 0.01 (1) | 0.01 (1) | 0.00 (1) | 0.00 (1) |
| oh-my-pi@18.18.3 | 15 | 310,664 | 5.31 (12) | 1.63 (12) | 0.58 (14) | 0.49 (14) |
| open-claw-reasoning@2026.11.1 | 2 | 1,447 | 0.01 (2) | 0.00 (2) | 0.00 (2) | 0.00 (2) |
| openclaw@2026.10.4 | 6 | 571,499 | 2.14 (6) | 1.83 (6) | 0.64 (6) | 0.61 (6) |
| openclaw@2026.11.1 | 20 | 829,535 | 2.01 (19) | 1.80 (20) | 0.65 (20) | 0.55 (20) |
| opencode@1.19.0 | 13 | 827,866 | 2.33 (13) | 1.73 (13) | 0.72 (13) | 0.65 (13) |
| opencode@2.2.6 | 19 | 352,083 | 4.99 (18) | 1.73 (17) | 0.54 (19) | 0.52 (19) |
| pi@1.2.0 | 5 | 290,506 | 1.58 (5) | 1.22 (5) | 0.45 (5) | 0.44 (5) |
| qwen-code@0.25.2 | 11 | 76,258 | 0.53 (10) | 0.37 (9) | 0.15 (11) | 0.15 (11) |

## Slice check

Runs with both a full replay and a recombined six-slice replay. Slicing drops the overlap between trials at slice boundaries.

| Run | Router | Prefix reuse full / sliced | Prefill full / sliced | Requests meeting SLA full / sliced | p99 TTFT full / sliced |
| --- | --- | ---: | ---: | ---: | ---: |
| `20261020-011837-deepseek-v4-1-flash-full-low-7d5f` | Round-robin | 93.3% / 93.3% | 1,560M / 1,564M | 99.9% / 99.9% | 1,183 / 1,216 ms |
| `20261020-011837-deepseek-v4-1-flash-full-low-7d5f` | KV router (defaults) | 94.8% / 94.8% | 1,219M / 1,208M | 99.4% / 99.4% | 1,612 / 1,689 ms |
| `20261020-011837-deepseek-v4-1-flash-full-low-7d5f` | KV router, prefill_load_scale 16 | 98.1% / 98.1% | 441M / 440M | 100.0% / 100.0% | 428 / 461 ms |
| `20261020-011837-deepseek-v4-1-flash-full-low-7d5f` | KV router + session affinity | 98.1% / 98.1% | 438M / 439M | 100.0% / 100.0% | 429 / 482 ms |
| `20261020-011839-deepseek-v4-1-flash-full-high-23dc` | Round-robin | 93.6% / 93.6% | 1,916M / 1,918M | 99.8% / 99.8% | 1,317 / 1,355 ms |
| `20261020-011839-deepseek-v4-1-flash-full-high-23dc` | KV router (defaults) | 94.8% / 94.9% | 1,549M / 1,533M | 99.3% / 99.2% | 1,728 / 1,820 ms |
| `20261020-011839-deepseek-v4-1-flash-full-high-23dc` | KV router, prefill_load_scale 16 | 98.2% / 98.2% | 549M / 549M | 100.0% / 100.0% | 493 / 555 ms |
| `20261020-011839-deepseek-v4-1-flash-full-high-23dc` | KV router + session affinity | 98.2% / 98.2% | 543M / 543M | 99.9% / 99.9% | 503 / 556 ms |
| `20261030-130307-deepseek-v4-1-flash-full-low-45b5` | Round-robin | 95.8% / 95.7% | 370M / 372M | 100.0% / 100.0% | 846 / 934 ms |
| `20261030-130307-deepseek-v4-1-flash-full-low-45b5` | KV router (defaults) | 97.6% / 97.7% | 208M / 199M | 99.6% / 99.7% | 1,153 / 1,216 ms |
| `20261030-130307-deepseek-v4-1-flash-full-low-45b5` | KV router, prefill_load_scale 16 | 98.9% / 98.9% | 98M / 98M | 100.0% / 100.0% | 298 / 336 ms |
| `20261030-130307-deepseek-v4-1-flash-full-low-45b5` | KV router + session affinity | 98.9% / 98.9% | 99M / 99M | 100.0% / 100.0% | 298 / 338 ms |
| `20261030-130311-deepseek-v4-1-flash-full-high-f8e6` | Round-robin | 95.9% / 95.9% | 423M / 425M | 99.9% / 99.9% | 898 / 1,039 ms |
| `20261030-130311-deepseek-v4-1-flash-full-high-f8e6` | KV router (defaults) | 97.6% / 97.6% | 253M / 251M | 99.6% / 99.6% | 1,236 / 1,356 ms |
| `20261030-130311-deepseek-v4-1-flash-full-high-f8e6` | KV router, prefill_load_scale 16 | 98.9% / 98.9% | 113M / 113M | 100.0% / 100.0% | 320 / 365 ms |
| `20261030-130311-deepseek-v4-1-flash-full-high-f8e6` | KV router + session affinity | 98.9% / 98.9% | 113M / 114M | 100.0% / 100.0% | 325 / 365 ms |
| `20261106-173114-ripple-65b-preview-full-default-0cf6` | Round-robin | 95.0% / 94.9% | 2,578M / 2,629M | 99.6% / 99.6% | 1,344 / 1,482 ms |
| `20261106-173114-ripple-65b-preview-full-default-0cf6` | KV router (defaults) | 95.5% / 95.5% | 2,295M / 2,310M | 99.3% / 99.3% | 1,656 / 1,702 ms |
| `20261106-173114-ripple-65b-preview-full-default-0cf6` | KV router, prefill_load_scale 16 | 98.6% / 98.6% | 739M / 740M | 100.0% / 100.0% | 538 / 587 ms |
| `20261106-173114-ripple-65b-preview-full-default-0cf6` | KV router + session affinity | 98.6% / 98.5% | 741M / 754M | 99.8% / 99.8% | 501 / 625 ms |

## Endpoint windows (concurrent runs merged per endpoint)

| Router | Prefix reuse | Prefill tokens | Runs meeting SLA | Requests meeting SLA | Mean TTFT | Median run p99 TTFT | Worst run p99 TTFT | Median trial p50 | GPU-hours |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Round-robin | 76.0% | 51.66B | 0 of 13 | 76.1% | 60,906 ms | 696,946 ms | 2,318.7 s | 43.7 min | 2,361 |
| KV router (defaults) | 93.6% | 13.83B | 1 of 13 | 91.2% | 334 ms | 2,977 ms | 5.7 s | 29.6 min | 1,473 |
| KV router, prefill_load_scale 16 | 98.4% | 3.44B | 13 of 13 | 99.8% | 98 ms | 473 ms | 0.9 s | 22.2 min | 1,458 |
| KV router + session affinity | 98.7% | 2.87B | 13 of 13 | 99.7% | 93 ms | 444 ms | 1.0 s | 22.0 min | 1,456 |

Prefill relative to affinity, per run (median / p90): Round-robin 14.19x / 28.89x; KV router (defaults) 4.56x / 5.44x; KV router, prefill_load_scale 16 1.20x / 1.27x.
Provider cached share over the same runs: 89.7%.

SLA outcomes per run (Y meets, n misses; order: round-robin, KV router, KV with prefill_load_scale 16, affinity): nnYY 12, nYYY 1.

## DeepSeek-V4.1-Flash native cross-check

| Router | Prefix reuse | Prefill tokens | Runs meeting SLA | Requests meeting SLA | Mean TTFT | Median run p99 TTFT | Worst run p99 TTFT | Median trial p50 | GPU-hours |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Round-robin | 94.6% | 0.60B | 0 of 1 | 1.2% | 307 ms | 1,816 ms | 1.8 s | 82.1 min | 640 |
| KV router (defaults) | 95.4% | 0.51B | 0 of 1 | 1.4% | 304 ms | 2,558 ms | 2.6 s | 81.1 min | 640 |
| KV router, prefill_load_scale 16 | 98.4% | 0.18B | 0 of 1 | 1.3% | 145 ms | 745 ms | 0.7 s | 75.9 min | 640 |
| KV router + session affinity | 98.5% | 0.16B | 0 of 1 | 1.3% | 139 ms | 571 ms | 0.6 s | 75.8 min | 637 |

Prefill relative to affinity, per run (median / p90): Round-robin 3.70x / 3.70x; KV router (defaults) 3.13x / 3.13x; KV router, prefill_load_scale 16 1.08x / 1.08x.
Provider cached share over the same runs: 98.9%.

