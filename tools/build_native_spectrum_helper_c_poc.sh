#!/usr/bin/env bash
set -euo pipefail

OUT_PATH="${1:-/tmp/native_spectrum_helper_c_poc}"
export TMPDIR="${TMPDIR:-/tmp}"

gcc \
  -O3 \
  -std=c11 \
  -Wall \
  -Wextra \
  -pedantic \
  tools/native_spectrum_helper_c_poc.c \
  -lm \
  -o "${OUT_PATH}"

echo "built=${OUT_PATH}"
