#!/bin/bash
# Build Dynamo and AISimulate from main into $W/venv. The study's build was Dynamo 3e84909a
# (ai-dynamo 1.7.0) with its pinned AISimulate 0.13.0.dev202610290000000087.
# Needs build-essential, pkg-config, libssl-dev, clang, cmake, protobuf-compiler, git, curl,
# python3-venv, python3-dev, libhwloc-dev, libudev-dev and libclang-dev (Ubuntu 24.04 package names).
set -euxo pipefail
W="${WORKDIR:-$PWD}"
command -v cargo || { curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal; }
source $HOME/.cargo/env
command -v uv || { curl -LsSf https://astral.sh/uv/install.sh | sh; }
export PATH=$HOME/.local/bin:$PATH
cd $W
[ -d dynamo ] || git clone --depth 1 https://github.com/ai-dynamo/dynamo.git
[ -d aisimulate ] || git clone --depth 1 https://github.com/ai-dynamo/aisimulate.git
git -C dynamo rev-parse HEAD > dynamo.rev; git -C aisimulate rev-parse HEAD > aisimulate.rev
[ -d venv ] || uv venv venv --python 3.12
source venv/bin/activate
uv pip install pip 'maturin[patchelf]'
export CARGO_BUILD_JOBS="${CARGO_BUILD_JOBS:-40}"
# ais-forward-pass links AISimulate's forward-pass model into the mocker; default (op-level) timing needs it.
(cd dynamo/lib/bindings/python && maturin develop --uv --release --features ais-forward-pass)
uv pip install -e dynamo/lib/gpu_memory_service || echo "gpu_memory_service install failed; continuing"
uv pip install -e dynamo
uv pip install -e aisimulate/python/aisimulate
# The Dynamo stack's Planner adapter imports scikit-learn, which no extra declares.
uv pip install scikit-learn
aisimulate --help | head -5
echo BUILD_OK
