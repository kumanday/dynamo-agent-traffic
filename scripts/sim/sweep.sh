#!/bin/bash
# Usage: sweep.sh NAME TRACE WORKERS POLICY   (POLICY: rr | kv | aff | kvpN, KV router with prefill_load_scale N)
# Run from the directory that holds glm-b300-op.yaml and the traces, inside the environment built by build.sh.
set -u
NAME=$1 TRACE=$2 W=$3 P=$4
OUT=sweep/$NAME
mkdir -p $OUT
python3 - "$TRACE" "$OUT/config.yaml" <<PY
import sys, yaml
d = yaml.safe_load(open("glm-b300-op.yaml"))
d["traffic"]["source"]["paths"] = [sys.argv[1]]
yaml.safe_dump(d, open(sys.argv[2], "w"), sort_keys=False)
PY
ARGS=(--set "engine.workers.aggregated.parallelism.replicas=$W")
case $P in
  rr)  ARGS+=(--set "router.policy=round_robin") ;;
  kv)  ARGS+=(--set "router.policy=kv_router") ;;
  aff) ARGS+=(--set "router.policy=kv_router" --set "router.conversation_affinity={mode: session, ttl_seconds: 300}") ;;
  kvp*) ARGS+=(--set "router.policy=kv_router" --set "router.prefill_load_scale=${P#kvp}") ;;
esac
date -u +%FT%TZ > $OUT/started
/usr/bin/time -v aisimulate predict --stack dynamo --config $OUT/config.yaml --output-dir $OUT --overwrite \
  --capture-per-request --format json "${ARGS[@]}" > $OUT/stdout.json 2> $OUT/stderr.log
echo $? > $OUT/exit
date -u +%FT%TZ > $OUT/finished
