# Full-dataset Dynamo replay

240 leaderboard runs, 69,923 trials, 6,947,564 requests per router. A replay meets the SLA when at least 99% of its requests meet 2 s TTFT and 50 ms inter-token latency.

14 runs were replayed as consecutive trial slices and recombined: `20261018-191102-glm-5-3-flash-full-high-0df9`, `20261020-011837-deepseek-v4-1-flash-full-low-7d5f`, `20261020-011839-deepseek-v4-1-flash-full-high-23dc`, `20261025-161003-flint-full-default-5596`, `20261112-101850-ripple-65b-preview-full-default-089d`, `20261112-230704-ripple-65b-preview-full-default-4f16`, `20261115-140852-ripple-65b-preview-full-default-6320`, `20261115-210123-ripple-65b-preview-full-default-8980`, `20261115-231927-glm-5-3-flash-full-high-32b6`, `20261115-232049-deepseek-v4-1-flash-full-low-74f3`, `20261115-232113-deepseek-v4-1-flash-full-high-d77f`, `20261117-085122-ripple-65b-preview-full-default-785d`, `20261117-085218-flint-full-default-1880`, `20261119-214509-flint-full-default-0b76`.

## All leaderboard runs

| Router | Prefix reuse | Prefill tokens | Runs meeting SLA | Requests meeting SLA | Mean TTFT | Median run p99 TTFT | Worst run p99 TTFT | Median trial p50 | GPU-hours |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Round-robin | 92.7% | 47.77B | 220 of 240 | 96.8% | 6,343 ms | 1,044 ms | 1,002.6 s | 13.5 min | 13,266 |
| KV router (defaults) | 95.9% | 26.64B | 211 of 240 | 98.3% | 183 ms | 833 ms | 5.5 s | 13.2 min | 12,845 |
| KV router, prefill_load_scale 16 | 98.6% | 9.23B | 240 of 240 | 99.9% | 83 ms | 378 ms | 1.3 s | 13.2 min | 12,828 |
| KV router + session affinity | 98.6% | 8.85B | 240 of 240 | 99.9% | 83 ms | 381 ms | 1.8 s | 12.9 min | 12,830 |

Prefill relative to affinity, per run (median / p90): Round-robin 3.69x / 3.90x; KV router (defaults) 1.58x / 3.17x; KV router, prefill_load_scale 16 1.00x / 1.07x.
Provider cached share over the same runs: 91.8%.

SLA outcomes per run (Y meets, n misses; order: round-robin, KV router, KV with prefill_load_scale 16, affinity): YYYY 207, nnYY 16, YnYY 13, nYYY 4.

## Traffic from DeepSeek-V4.1-Flash

| Router | Prefix reuse | Prefill tokens | Runs meeting SLA | Requests meeting SLA | Mean TTFT | Median run p99 TTFT | Worst run p99 TTFT | Median trial p50 | GPU-hours |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Round-robin | 94.7% | 9.98B | 90 of 91 | 99.8% | 190 ms | 1,075 ms | 2.1 s | 13.2 min | 5,860 |
| KV router (defaults) | 95.9% | 7.59B | 82 of 91 | 99.4% | 168 ms | 789 ms | 2.7 s | 12.9 min | 5,847 |
| KV router, prefill_load_scale 16 | 98.5% | 2.77B | 91 of 91 | 100.0% | 82 ms | 359 ms | 1.3 s | 13.3 min | 5,848 |
| KV router + session affinity | 98.5% | 2.73B | 91 of 91 | 100.0% | 82 ms | 362 ms | 1.3 s | 13.1 min | 5,852 |

Prefill relative to affinity, per run (median / p90): Round-robin 3.74x / 3.87x; KV router (defaults) 1.57x / 3.13x; KV router, prefill_load_scale 16 1.00x / 1.03x.
Provider cached share over the same runs: 98.5%.

SLA outcomes per run (Y meets, n misses; order: round-robin, KV router, KV with prefill_load_scale 16, affinity): YYYY 81, YnYY 9, nYYY 1.

## Traffic from GLM-5.3-Flash (zai-org)

| Router | Prefix reuse | Prefill tokens | Runs meeting SLA | Requests meeting SLA | Mean TTFT | Median run p99 TTFT | Worst run p99 TTFT | Median trial p50 | GPU-hours |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Round-robin | 95.0% | 6.38B | 85 of 90 | 99.0% | 799 ms | 858 ms | 384.5 s | 11.0 min | 2,661 |
| KV router (defaults) | 96.0% | 5.13B | 84 of 90 | 99.4% | 147 ms | 612 ms | 4.5 s | 10.7 min | 2,635 |
| KV router, prefill_load_scale 16 | 98.6% | 1.84B | 90 of 90 | 100.0% | 76 ms | 343 ms | 1.3 s | 10.9 min | 2,632 |
| KV router + session affinity | 98.7% | 1.65B | 90 of 90 | 99.9% | 73 ms | 340 ms | 1.3 s | 10.8 min | 2,632 |

Prefill relative to affinity, per run (median / p90): Round-robin 3.65x / 3.90x; KV router (defaults) 1.33x / 3.25x; KV router, prefill_load_scale 16 1.00x / 1.11x.
Provider cached share over the same runs: 96.4%.

SLA outcomes per run (Y meets, n misses; order: round-robin, KV router, KV with prefill_load_scale 16, affinity): YYYY 83, nnYY 4, YnYY 2, nYYY 1.

## Traffic from Inkling-2-Small

| Router | Prefix reuse | Prefill tokens | Runs meeting SLA | Requests meeting SLA | Mean TTFT | Median run p99 TTFT | Worst run p99 TTFT | Median trial p50 | GPU-hours |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Round-robin | 94.9% | 0.07B | 2 of 2 | 99.9% | 200 ms | 1,095 ms | 1.1 s | 12.7 min | 58 |
| KV router (defaults) | 97.0% | 0.04B | 1 of 2 | 99.2% | 145 ms | 1,623 ms | 2.1 s | 12.4 min | 57 |
| KV router, prefill_load_scale 16 | 98.6% | 0.02B | 2 of 2 | 100.0% | 81 ms | 540 ms | 0.5 s | 12.4 min | 57 |
| KV router + session affinity | 98.6% | 0.02B | 2 of 2 | 100.0% | 81 ms | 549 ms | 0.6 s | 12.5 min | 57 |

Prefill relative to affinity, per run (median / p90): Round-robin 3.66x / 3.64x; KV router (defaults) 2.16x / 2.07x; KV router, prefill_load_scale 16 0.99x / 0.99x.
Provider cached share over the same runs: 93.3%.

SLA outcomes per run (Y meets, n misses; order: round-robin, KV router, KV with prefill_load_scale 16, affinity): YYYY 1, YnYY 1.

## Traffic from Ripple-65B-Preview

| Router | Prefix reuse | Prefill tokens | Runs meeting SLA | Requests meeting SLA | Mean TTFT | Median run p99 TTFT | Worst run p99 TTFT | Median trial p50 | GPU-hours |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Round-robin | 91.5% | 16.55B | 21 of 29 | 95.2% | 11,679 ms | 1,344 ms | 1,002.6 s | 24.6 min | 2,295 |
| KV router (defaults) | 95.7% | 8.31B | 22 of 29 | 98.2% | 215 ms | 1,495 ms | 4.5 s | 23.4 min | 2,097 |
| KV router, prefill_load_scale 16 | 98.5% | 2.82B | 29 of 29 | 99.8% | 95 ms | 467 ms | 1.2 s | 22.9 min | 2,084 |
| KV router + session affinity | 98.6% | 2.71B | 29 of 29 | 99.7% | 96 ms | 444 ms | 1.8 s | 23.3 min | 2,082 |

Prefill relative to affinity, per run (median / p90): Round-robin 3.55x / 3.88x; KV router (defaults) 2.43x / 3.23x; KV router, prefill_load_scale 16 1.00x / 1.08x.
Provider cached share over the same runs: 97.2%.

SLA outcomes per run (Y meets, n misses; order: round-robin, KV router, KV with prefill_load_scale 16, affinity): YYYY 20, nnYY 6, nYYY 2, YnYY 1.

## Traffic from flint

| Router | Prefix reuse | Prefill tokens | Runs meeting SLA | Requests meeting SLA | Mean TTFT | Median run p99 TTFT | Worst run p99 TTFT | Median trial p50 | GPU-hours |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Round-robin | 89.8% | 14.79B | 22 of 28 | 92.1% | 14,689 ms | 987 ms | 905.3 s | 16.9 min | 2,392 |
| KV router (defaults) | 96.1% | 5.57B | 22 of 28 | 95.6% | 207 ms | 911 ms | 5.5 s | 15.9 min | 2,209 |
| KV router, prefill_load_scale 16 | 98.8% | 1.78B | 28 of 28 | 99.9% | 80 ms | 405 ms | 0.9 s | 16.3 min | 2,208 |
| KV router + session affinity | 98.8% | 1.75B | 28 of 28 | 99.8% | 81 ms | 429 ms | 1.6 s | 16.3 min | 2,207 |

Prefill relative to affinity, per run (median / p90): Round-robin 3.62x / 3.95x; KV router (defaults) 1.69x / 2.97x; KV router, prefill_load_scale 16 1.00x / 1.12x.
Provider cached share over the same runs: 71.8%.

SLA outcomes per run (Y meets, n misses; order: round-robin, KV router, KV with prefill_load_scale 16, affinity): YYYY 22, nnYY 6.

## By harness (prefill tokens, billions; runs meeting SLA)

| Harness | Runs | Requests | Round-robin | KV router | KV, prefill_load_scale 16 | Affinity |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| None@2.4.6 | 2 | 1,937 | 0.01 (2) | 0.00 (2) | 0.00 (2) | 0.00 (2) |
| claude-code@2.1.300 | 16 | 1,153,209 | 5.97 (16) | 4.89 (15) | 1.70 (16) | 1.71 (16) |
| codex@0.162.1 | 5 | 19,262 | 0.07 (5) | 0.06 (5) | 0.02 (5) | 0.02 (5) |
| deepseek-harness@0.2.2-rc.1 | 20 | 390,430 | 7.70 (17) | 1.71 (17) | 0.51 (20) | 0.48 (20) |
| fx@0.0.16 | 21 | 137,977 | 4.68 (20) | 0.70 (20) | 0.22 (21) | 0.19 (21) |
| grok-build@1.0.77 | 9 | 543,220 | 2.95 (6) | 2.33 (6) | 0.90 (9) | 0.85 (9) |
| hermes@v0.22.1 | 27 | 364,783 | 5.05 (25) | 2.44 (19) | 0.63 (27) | 0.62 (27) |
| kimi-code@2.2.0 | 25 | 309,262 | 1.64 (22) | 1.20 (22) | 0.48 (25) | 0.48 (25) |
| mini-swe-agent@2.4.6 | 14 | 367,971 | 2.17 (14) | 1.73 (14) | 0.61 (14) | 0.61 (14) |
| open-claw-reasoning@2026.11.1 | 15 | 334,237 | 1.66 (13) | 1.41 (13) | 0.50 (15) | 0.50 (15) |
| openclaw@2026.10.4 | 11 | 910,500 | 3.94 (10) | 3.16 (10) | 1.13 (11) | 1.09 (11) |
| openclaw@2026.11.1 | 22 | 841,691 | 2.08 (21) | 1.84 (21) | 0.67 (22) | 0.57 (22) |
| opencode@1.19.0 | 17 | 881,333 | 3.02 (16) | 1.98 (16) | 0.79 (17) | 0.70 (17) |
| opencode@2.2.6 | 19 | 349,520 | 4.97 (18) | 1.72 (17) | 0.54 (19) | 0.52 (19) |
| pi@1.2.0 | 6 | 265,974 | 1.31 (5) | 1.11 (5) | 0.38 (6) | 0.36 (6) |
| qwen-code@0.25.2 | 11 | 76,258 | 0.53 (10) | 0.37 (9) | 0.15 (11) | 0.15 (11) |

## Slice check

Runs with both a full replay and a recombined six-slice replay. Slicing drops the overlap between trials at slice boundaries.

| Run | Router | Prefix reuse full / sliced | Prefill full / sliced | Requests meeting SLA full / sliced | p99 TTFT full / sliced |
| --- | --- | ---: | ---: | ---: | ---: |
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
| Round-robin | 77.2% | 43.80B | 3 of 16 | 76.7% | 53,599 ms | 598,999 ms | 2,228.5 s | 39.9 min | 2,199 |
| KV router (defaults) | 93.5% | 12.46B | 4 of 16 | 90.3% | 347 ms | 2,572 ms | 5.7 s | 26.2 min | 1,451 |
| KV router, prefill_load_scale 16 | 98.4% | 3.03B | 16 of 16 | 99.9% | 98 ms | 500 ms | 0.8 s | 19.4 min | 1,427 |
| KV router + session affinity | 98.7% | 2.49B | 16 of 16 | 99.8% | 92 ms | 440 ms | 1.1 s | 19.6 min | 1,424 |

Prefill relative to affinity, per run (median / p90): Round-robin 12.82x / 28.29x; KV router (defaults) 4.05x / 6.64x; KV router, prefill_load_scale 16 1.21x / 1.44x.
Provider cached share over the same runs: 92.9%.

SLA outcomes per run (Y meets, n misses; order: round-robin, KV router, KV with prefill_load_scale 16, affinity): nnYY 12, YYYY 3, nYYY 1.

## DeepSeek-V4.1-Flash native cross-check

| Router | Prefix reuse | Prefill tokens | Runs meeting SLA | Requests meeting SLA | Mean TTFT | Median run p99 TTFT | Worst run p99 TTFT | Median trial p50 | GPU-hours |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Round-robin | 94.6% | 0.60B | 0 of 1 | 1.2% | 307 ms | 1,816 ms | 1.8 s | 82.1 min | 640 |
| KV router (defaults) | 95.4% | 0.51B | 0 of 1 | 1.4% | 304 ms | 2,558 ms | 2.6 s | 81.1 min | 640 |
| KV router, prefill_load_scale 16 | 98.4% | 0.18B | 0 of 1 | 1.3% | 145 ms | 745 ms | 0.7 s | 75.9 min | 640 |
| KV router + session affinity | 98.5% | 0.16B | 0 of 1 | 1.3% | 139 ms | 571 ms | 0.6 s | 75.8 min | 637 |

Prefill relative to affinity, per run (median / p90): Round-robin 3.70x / 3.70x; KV router (defaults) 3.13x / 3.13x; KV router, prefill_load_scale 16 1.08x / 1.08x.
Provider cached share over the same runs: 98.9%.

