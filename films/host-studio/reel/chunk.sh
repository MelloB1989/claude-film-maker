#!/bin/bash
# one bridge-lock hold for a render chunk: run from tools/ under run.sh. Args: shots (comma list); env BUILD=1 runs build.py, PRE=1
# install + relight + check stills first.
set -e
if [ "${BUILD:-}" = 1 ]; then uv run python ../films/host-studio/reel/build.py | tail -1; fi
if [ "${PRE:-}" = 1 ]; then
  uv run film-ue install | tail -1
  uv run python ../films/host-studio/reel/light.py --seq /Game/Reel/SEQ_Reel | tail -2
  uv run python ../films/host-studio/reel/halo_check.py --camera Reel_V03 --frames 420 | tail -1
  uv run python ../films/host-studio/reel/halo_check.py --camera Reel_N01 --frames 900 | tail -1
fi
uv run python ../films/host-studio/reel/render.py --shots "$1"
