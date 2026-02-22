#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Run native spectrum-helper POC perf scenarios.

Usage:
  tools/run_native_spectrum_helper_poc_bench.sh [options]

Options:
  --helper stub|c        Helper implementation to use (default: c)
  --media-dir PATH       Override perf media corpus path (defaults to .local/perf_media)
  --label LABEL          Perf run label suffix (default: native-helper-poc)
  --repeat N             Scenario repeat count (default: 1)
  --scenario NAME        Perf scenario (default: analysis-cache)
                        Supported: analysis-cache, analysis-bundle-sw
  --timeout-s SECONDS    Helper timeout (default: 30 for stub, 8 for c)
  --python PATH          Python executable (default: .ubuntu-venv/bin/python)
  -h, --help             Show this help text

Examples:
  tools/run_native_spectrum_helper_poc_bench.sh --helper stub --timeout-s 30
  tools/run_native_spectrum_helper_poc_bench.sh --helper c --media-dir /tmp/tz_player_perf_mp3_subset
EOF
}

HELPER_KIND="c"
MEDIA_DIR=""
LABEL="native-helper-poc"
REPEAT="1"
SCENARIO="analysis-cache"
TIMEOUT_S=""
PYTHON_BIN=".ubuntu-venv/bin/python"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --helper)
      HELPER_KIND="${2:?missing value for --helper}"
      shift 2
      ;;
    --media-dir)
      MEDIA_DIR="${2:?missing value for --media-dir}"
      shift 2
      ;;
    --label)
      LABEL="${2:?missing value for --label}"
      shift 2
      ;;
    --repeat)
      REPEAT="${2:?missing value for --repeat}"
      shift 2
      ;;
    --scenario)
      SCENARIO="${2:?missing value for --scenario}"
      shift 2
      ;;
    --timeout-s)
      TIMEOUT_S="${2:?missing value for --timeout-s}"
      shift 2
      ;;
    --python)
      PYTHON_BIN="${2:?missing value for --python}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "${HELPER_KIND}" in
  stub|c) ;;
  *)
    echo "invalid --helper value: ${HELPER_KIND} (expected stub|c)" >&2
    exit 2
    ;;
esac

case "${SCENARIO}" in
  analysis-cache|analysis-bundle-sw) ;;
  *)
    echo "invalid --scenario value: ${SCENARIO} (expected analysis-cache|analysis-bundle-sw)" >&2
    exit 2
    ;;
esac

if [[ -z "${TIMEOUT_S}" ]]; then
  if [[ "${HELPER_KIND}" == "stub" ]]; then
    TIMEOUT_S="30"
  else
    TIMEOUT_S="8"
  fi
fi

HELPER_CMD=""
if [[ "${HELPER_KIND}" == "stub" ]]; then
  HELPER_CMD="${PYTHON_BIN} tools/native_spectrum_helper_stub.py"
else
  HELPER_BIN="/tmp/native_spectrum_helper_c_poc"
  bash tools/build_native_spectrum_helper_c_poc.sh "${HELPER_BIN}" >/tmp/native_spectrum_helper_c_poc_build.log
  HELPER_CMD="${HELPER_BIN}"
fi

echo "helper_kind=${HELPER_KIND}"
echo "helper_cmd=${HELPER_CMD}"
echo "helper_timeout_s=${TIMEOUT_S}"
echo "repeat=${REPEAT}"
echo "scenario=${SCENARIO}"
if [[ -n "${MEDIA_DIR}" ]]; then
  echo "media_dir=${MEDIA_DIR}"
fi

ENV_ARGS=(
  "TZ_PLAYER_RUN_PERF=1"
  "TZ_PLAYER_NATIVE_SPECTRUM_HELPER_CMD=${HELPER_CMD}"
  "TZ_PLAYER_NATIVE_SPECTRUM_HELPER_TIMEOUT_S=${TIMEOUT_S}"
)
if [[ -n "${MEDIA_DIR}" ]]; then
  ENV_ARGS+=("TZ_PLAYER_PERF_MEDIA_DIR=${MEDIA_DIR}")
fi

env "${ENV_ARGS[@]}" \
  "${PYTHON_BIN}" tools/perf_run.py \
  --scenario "${SCENARIO}" \
  --repeat "${REPEAT}" \
  --label "${LABEL}-${SCENARIO}-${HELPER_KIND}"
