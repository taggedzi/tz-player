#!/usr/bin/env bash
set -euo pipefail

OUT_PATH="${1:-/tmp/tz_player_native_helper}"
export TMPDIR="${TMPDIR:-/tmp}"

gcc \
  -O3 \
  -std=c11 \
  -Wall \
  -Wextra \
  -pedantic \
  tools/tz_player_native_helper.c \
  -lm \
  -o "${OUT_PATH}"

echo "built=${OUT_PATH}"
