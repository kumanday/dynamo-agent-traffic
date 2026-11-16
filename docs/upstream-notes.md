# Technical notes for Dynamo and AISimulate maintainers

Four observations from replaying Harness Leaderboard agent traffic through `aisimulate predict --stack dynamo`. The study and its limits are described in the [report](https://kumanday.github.io/dynamo-agent-traffic/).

Everything here was observed on Dynamo `3e84909a` (ai-dynamo 1.7.0) with the AISimulate release it pins, `0.13.0.dev202610290000000087`.

## 1. Dynamo: the replay runner rejects engine model controls

`--stack dynamo` rejects `kvcache_quant_mode` and `fmha_quant_mode` because `DynamoReplayRunnerFactory` does not advertise engine model controls.

`DynamoReplayRunnerFactory.capabilities()` in `components/src/dynamo/replay/simulation.py` copies most of `EngineReplayRunnerFactory().capabilities()` but leaves `supported_engine_model_controls` at its empty default. AISimulate's capability check then rejects every quantization and kernel selector:

```text
runs/smoke20.yaml: runner does not support engine model controls ['kvcache_quant_mode', 'fmha_quant_mode']; use --stack engine
```

This blocks two GLM-5.3-Flash setups on the Dynamo stack:

- H200 with vLLM 0.31.0 needs `kvcache_quant_mode: bfloat16`. Without the control, the model resolves FP8 KV, and the engine rejects FP8 sparse-MLA KV on SM90 before vLLM 0.32.0.
- The published Blackwell FPM profiles record `fmha_quant_mode: fp8`, while the default resolution is `bfloat16`, so the FPM cell lookup fails on identity.

Forwarding the engine runner's tuple fixes the gate ([dynamo-engine-model-controls.patch](../scripts/sim/dynamo-engine-model-controls.patch)):

```python
supported_engine_model_controls=(
    engine_capabilities.supported_engine_model_controls
),
```

With the patch, the B300 FPM identity resolves and the run reaches the timing model. The results in the report use stock Dynamo on B300, where FP8 KV is the default, and operator-level timing.

Open question: does the Dynamo mocker apply every control in `ENGINE_MODEL_CONTROL_FIELDS`, or only the quantization modes?

## 2. Dynamo: the KV router gives up cached prefixes on long-context agent traffic

Under load, the default KV router cost abandons 100k-token cached prefixes. On 6.6M agent requests, session affinity or `prefill_load_scale` 16 cuts prefill to about a third and SLA misses from 22 runs to 1.

Setup: `aisimulate predict --stack dynamo`, GLM-5.3-Flash FP8 on B300 TP2 workers, vLLM 0.31.0, operator-level timing. The pilot traffic is two full Harness Leaderboard runs converted to agentic Mooncake v2 from per-call proxy logs: 84,444 and 92,744 requests, 526-528 coding-agent trials, 155-273 trials at peak, mean prompt about 100k tokens, closed-loop pacing with recorded tool gaps.

Hermes run, 4 workers (8 GPUs):

| Router | Prefix reuse | Prefill tokens | TTFT mean / p99 | Median trial |
| --- | ---: | ---: | ---: | ---: |
| Round-robin | 66.1% | 3,101.4M | 94.7 s / 948 s | 453.0 min |
| KV router (defaults) | 90.0% | 912.4M | 849 ms / 6.5 s | 101.1 min |
| KV router, `prefill_load_scale` 4 | 96.3% | 334.0M | 262 ms / 3.3 s | 63.0 min |
| KV router, `prefill_load_scale` 16 | 98.0% | 184.7M | 151 ms / 1,202 ms | 54.5 min |
| KV router + `conversation_affinity` (session, 300 s) | 98.6% | 130.4M | 129 ms / 889 ms | 51.4 min |

With affinity, 8 GPUs beat the default KV router on 16 GPUs: p99 TTFT 889 ms against 5.0 s, and 130.4M against 838.1M prefill tokens. On the OpenClaw run, going from 4 to 8 workers raises default-router prefill from 157.4M to 276.9M tokens, while affinity stays at 41.5M and 41.6M.

Across the whole leaderboard (216 runs, 68,905 trials, 6,616,606 requests per router, each run on at least one 8-GPU node):

| Router | Prefill tokens | Runs meeting SLA | Endpoint windows meeting SLA |
| --- | ---: | ---: | ---: |
| Round-robin | 49.2B | 201 of 216 | 0 of 13 |
| KV router (defaults) | 25.5B | 194 of 216 | 1 of 13 |
| KV router, `prefill_load_scale` 16 | 8.7B | 215 of 216 | 13 of 13 |
| KV router + session affinity | 8.3B | 215 of 216 | 13 of 13 |

A replay meets the SLA when at least 99% of its requests are within 2 s TTFT and 50 ms ITL. In 21 runs the default router misses the SLA where affinity meets it, and no run goes the other way. The endpoint windows merge runs that loaded the same provider endpoint at the same time.

Mechanism: the cost adds `prefill_load_scale × adjusted_prefill_blocks` to `potential_decode_blocks`. An active agent request carries about 1,500 blocks of context, so one or two extra long sessions on the cache-holding worker outweigh recomputing the whole prompt elsewhere. For hybrid or sparse-attention models such as GLM-5.3-Flash, decode cost also grows more slowly with context than the block count suggests.

Possible directions:

- Default `conversation_affinity` for requests that carry agent session lineage, which the 1.6 session-aware indexer already tracks.
- Scale the overlap credit by prompt length, or bound the decode term per request, so a long cached prefix cannot be outbid by modest decode imbalance.
- A 1.7 router-plugin scorer that prices decode load by the model's attention cost and leaves raw block counts aside.

These numbers come from the simulator's operator-level timing model. No request ran on a GPU.

## 3. AISimulate: Harness Leaderboard meter logs as an agentic trace source

The public `joelniklaus/harness-leaderboard` bucket records every model call of every trial in `agent/hlb-meter.jsonl`: start time, TTFB, latency, and input, cached, output and reasoning tokens. It covers 14 coding-agent harnesses on open-weights models, with hundreds of concurrent trials per run. [hlb_to_agentic.py](../scripts/hlb_to_agentic.py) converts those logs to agentic Mooncake v2 traces with:

- one play per trial
- sessions per conversation stream, with spawn and join edges for parallel calls and subagents
- completion dependencies delayed by the recorded tool gap
- `hash_ids` synthesized from token counts, either append-only or bounded by the provider's cached count, with a shared per-harness system-prompt chain
- `recorded_api_time_ms` from the logged latency

Validation: on DeepInfra's DeepSeek-V4.1-Flash endpoint, the provider's cached share is within 0.5 points of the append-only reuse for all 12 harnesses. The converted OpenClaw run reproduces the provider's 98.8% cached share in the lower-bound trace and replays end to end on the Dynamo stack.

AISimulate's documentation says trace converters belong in AISimulate. This converter is a single file with no dependency outside the Python standard library.

## 4. AISimulate: CLI supervisor cost and orphaned execution processes

Observed while running 160 concurrent `predict --stack dynamo` replays on a 176-vCPU machine:

- **Supervisor CPU.** Each supervisor (`aisimulate predict`) used 5,498 CPU-seconds over 13,319 seconds of wall time, about 41% of a core. Its execution process (`python -m aisimulate.resource_worker cli predict`) used 10,162 CPU-seconds. Across 160 replays, supervision took about 65 cores. Lowering only the supervisors' priority (`renice 15`) doubled the replay completion rate. A configurable or adaptive resource-polling interval would help large sweeps.
- **Orphans.** Sending SIGTERM to the supervisors left 153 execution processes running, reparented to PID 1 and still computing 16 minutes later. Starting the execution process in its own process group and terminating that group on SIGTERM or SIGINT would prevent this.
- **Initialization timeout.** With many replays starting together, trace parsing for large agentic traces (up to 488,000 requests) exceeded the 60-second `execution.resources.initialization_timeout_seconds` default, and runs exited with code 124. Raising it to 1,800 seconds fixed this; the timeout could scale with trace size.
