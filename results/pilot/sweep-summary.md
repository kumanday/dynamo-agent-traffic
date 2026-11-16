| Trace | Workers (GPUs) | Router | Requests | Prefix reuse | Prefill tokens | TTFT mean / p90 / p99 (ms) | ITL mean / p99 (ms) | Trial time p50 / p90 (min) |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| calib-glm100 | 4 (8) | round-robin | 13,085 | 98.4% | 18.7M | 75 / 122 / 326 | 9.3 / 13.0 | 10.2 / 64.4 |
| calib-glm100 | 4 (8) | KV router | 13,085 | 98.6% | 16.5M | 72 / 118 / 458 | 8.9 / 11.7 | 10.2 / 64.1 |
| calib-glm100 | 8 (16) | round-robin | 13,085 | 96.9% | 36.0M | 108 / 205 / 550 | 8.1 / 10.9 | 9.2 / 64.0 |
| calib-glm100 | 8 (16) | KV router | 13,085 | 98.4% | 19.2M | 72 / 119 / 610 | 7.5 / 9.2 | 9.4 / 62.2 |
| calib-glm100 | 8 (16) | KV router + session affinity | 13,085 | 99.6% | 5.2M | 44 / 62 / 108 | 7.8 / 10.2 | 9.3 / 61.6 |
| calib-glm100 | 16 (32) | round-robin | 13,085 | 94.2% | 68.0M | 175 / 384 / 952 | 7.4 / 10.2 | 8.9 / 62.7 |
| calib-glm100 | 16 (32) | KV router | 13,085 | 98.9% | 12.7M | 56 / 75 / 438 | 7.0 / 8.8 | 8.9 / 60.5 |
| calib-glm100 | 16 (32) | KV router + session affinity | 13,085 | 99.6% | 5.2M | 43 / 61 / 110 | 7.7 / 10.2 | 9.5 / 60.9 |
| calib-glm100 | 32 (64) | round-robin | 13,085 | 89.2% | 125.5M | 301 / 686 / 1,586 | 7.0 / 8.8 | 8.8 / 62.9 |
| calib-glm100 | 32 (64) | KV router | 13,085 | 98.9% | 13.4M | 57 / 78 / 455 | 7.0 / 8.8 | 9.0 / 60.5 |
| calib-glm100 | 32 (64) | KV router + session affinity | 13,085 | 99.6% | 5.2M | 43 / 61 / 108 | 7.7 / 10.2 | 9.7 / 61.2 |
| calib-hermes100 | 4 (8) | round-robin | 15,165 | 95.2% | 76.8M | 203 / 436 / 1,569 | 14.0 / 83.5 | 35.8 / 86.3 |
| calib-hermes100 | 4 (8) | KV router | 15,165 | 95.8% | 67.2M | 205 / 453 / 1,924 | 13.6 / 72.2 | 34.7 / 85.1 |
| calib-hermes100 | 8 (16) | round-robin | 15,165 | 90.9% | 146.7M | 333 / 850 / 2,476 | 11.3 / 15.8 | 30.7 / 80.5 |
| calib-hermes100 | 8 (16) | KV router | 15,165 | 94.0% | 97.1M | 256 / 643 / 2,540 | 10.3 / 13.0 | 29.4 / 78.9 |
| calib-hermes100 | 8 (16) | KV router + session affinity | 15,165 | 98.7% | 21.0M | 81 / 116 / 528 | 9.6 / 13.6 | 28.6 / 77.2 |
| calib-hermes100 | 16 (32) | round-robin | 15,165 | 83.3% | 269.5M | 565 / 1,452 / 3,717 | 9.4 / 11.8 | 28.6 / 78.1 |
| calib-hermes100 | 16 (32) | KV router | 15,165 | 93.7% | 101.2M | 246 / 657 / 2,832 | 8.1 / 10.2 | 28.1 / 74.5 |
| calib-hermes100 | 16 (32) | KV router + session affinity | 15,165 | 98.7% | 20.3M | 72 / 109 / 481 | 8.1 / 10.9 | 27.6 / 74.5 |
| calib-hermes100 | 32 (64) | round-robin | 15,165 | 71.7% | 457.3M | 915 / 2,400 / 4,745 | 8.2 / 10.3 | 28.3 / 78.0 |
| calib-hermes100 | 32 (64) | KV router | 15,165 | 96.7% | 54.0M | 135 / 258 / 1,737 | 7.0 / 8.8 | 23.5 / 72.7 |
| calib-hermes100 | 32 (64) | KV router + session affinity | 15,165 | 98.8% | 19.6M | 68 / 106 / 441 | 7.5 / 8.9 | 25.0 / 73.2 |
| flint-hermes-upper | 4 (8) | round-robin | 84,444 | 66.1% | 3,101.4M | 94,689 / 517,732 / 947,877 | 62.6 / 275.1 | 453.0 / 696.5 |
| flint-hermes-upper | 4 (8) | KV router | 84,444 | 90.0% | 912.4M | 849 / 3,172 / 6,479 | 46.2 / 271.8 | 101.1 / 179.1 |
| flint-hermes-upper | 4 (8) | KV router, prefill_load_scale 4 | 84,444 | 96.3% | 334.0M | 262 / 520 / 3,327 | 27.0 / 259.6 | 63.0 / 120.3 |
| flint-hermes-upper | 4 (8) | KV router, prefill_load_scale 16 | 84,444 | 98.0% | 184.7M | 151 / 231 / 1,202 | 23.2 / 166.2 | 54.5 / 108.4 |
| flint-hermes-upper | 4 (8) | KV router + session affinity | 84,444 | 98.6% | 130.4M | 129 / 166 / 889 | 21.8 / 102.6 | 51.4 / 104.1 |
| flint-hermes-upper | 8 (16) | round-robin | 84,444 | 69.5% | 2,785.6M | 29,325 / 6,133 / 670,275 | 40.0 / 271.8 | 170.8 / 325.2 |
| flint-hermes-upper | 8 (16) | KV router | 84,444 | 90.8% | 838.1M | 514 / 1,364 / 5,021 | 22.3 / 256.5 | 54.9 / 108.2 |
| flint-hermes-upper | 8 (16) | KV router + session affinity | 84,444 | 98.6% | 130.0M | 107 / 137 / 693 | 14.6 / 62.9 | 37.5 / 85.7 |
| glm-openclaw-lower | 4 (8) | KV router | 92,744 | 96.3% | 337.7M | 215 / 413 / 2,457 | 19.2 / 201.7 | 32.5 / 118.2 |
| glm-openclaw-upper | 4 (8) | round-robin | 92,744 | 98.2% | 161.8M | 106 / 156 / 643 | 17.0 / 89.7 | 30.6 / 111.0 |
| glm-openclaw-upper | 4 (8) | KV router | 92,744 | 98.3% | 157.4M | 112 / 186 / 677 | 16.7 / 86.1 | 30.5 / 109.2 |
| glm-openclaw-upper | 4 (8) | KV router, prefill_load_scale 4 | 92,744 | 98.6% | 129.9M | 99 / 160 / 550 | 16.5 / 80.1 | 30.5 / 108.2 |
| glm-openclaw-upper | 4 (8) | KV router, prefill_load_scale 16 | 92,744 | 99.2% | 71.6M | 74 / 108 / 321 | 16.0 / 64.8 | 29.9 / 105.8 |
| glm-openclaw-upper | 4 (8) | KV router + session affinity | 92,744 | 99.5% | 41.5M | 62 / 83 / 154 | 15.4 / 55.6 | 28.7 / 105.0 |
| glm-openclaw-upper | 8 (16) | round-robin | 92,744 | 96.6% | 307.1M | 142 / 252 / 846 | 12.6 / 63.5 | 26.0 / 95.1 |
| glm-openclaw-upper | 8 (16) | KV router | 92,744 | 96.9% | 276.9M | 146 / 311 / 997 | 12.1 / 49.2 | 25.8 / 93.3 |
| glm-openclaw-upper | 8 (16) | KV router + session affinity | 92,744 | 99.5% | 41.6M | 55 / 73 / 136 | 11.1 / 34.9 | 24.3 / 89.5 |
