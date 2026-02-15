#!/usr/bin/env bash
set -euo pipefail

if [[ -x ".ubuntu-venv/bin/python" ]]; then
  exec .ubuntu-venv/bin/python tools/release.py "$@"
fi

exec python tools/release.py "$@"
