#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Build the native spectrum helper.

Usage:
  tools/build_native_spectrum_helper.sh [OUT_PATH]
  tools/build_native_spectrum_helper.sh --out-dir DIR

Defaults to the packaged helper path under src/tz_player/binaries.
EOF
}

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"
default_out_dir="${repo_root}/src/tz_player/binaries/linux/x86_64"
out_path=""

if [[ $# -gt 0 ]]; then
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --out-dir)
      out_dir="${2:?missing value for --out-dir}"
      out_path="${out_dir%/}/tz_player_native_helper"
      shift 2
      ;;
    *)
      out_path="$1"
      shift 1
      ;;
  esac
fi

if [[ -z "${out_path}" ]]; then
  out_path="${default_out_dir}/tz_player_native_helper"
fi

mkdir -p "$(dirname -- "${out_path}")"
export TMPDIR="${TMPDIR:-/tmp}"

gcc \
  -O3 \
  -std=c11 \
  -Wall \
  -Wextra \
  -pedantic \
  tools/tz_player_native_helper.c \
  -lm \
  -o "${out_path}"

echo "built=${out_path}"
