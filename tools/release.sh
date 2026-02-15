#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "${script_dir}/.." && pwd)"
release_py="${script_dir}/release.py"

cd "${repo_root}"

if [[ -x "${repo_root}/.ubuntu-venv/bin/python" ]]; then
  exec "${repo_root}/.ubuntu-venv/bin/python" "${release_py}" "$@"
fi

if command -v python >/dev/null 2>&1; then
  exec python "${release_py}" "$@"
fi

if command -v python3 >/dev/null 2>&1; then
  exec python3 "${release_py}" "$@"
fi

echo "ERROR: No Python interpreter found (expected python or python3)." >&2
exit 127
