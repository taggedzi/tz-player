#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  tools/release.sh <version>

Examples:
  tools/release.sh 0.5.2
  tools/release.sh v0.5.2

What it does:
  1) Validates clean git state and required tools.
  2) Updates version + changelog from commit history.
  3) Runs release quality checks.
  4) Creates/pushes a release branch and PR.
  5) Waits for PR checks, merges PR.
  6) Creates/pushes release tag v<version>.
  7) Tag push triggers GitHub release workflow.
EOF
}

log() {
  printf '[release] %s\n' "$*"
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" || "${1:-}" == "" ]]; then
  usage
  exit 0
fi

raw_version="$1"
version="${raw_version#v}"
version="${version#V}"

if [[ -z "${version}" ]]; then
  echo "Version cannot be empty." >&2
  exit 1
fi

require_cmd git
require_cmd gh
require_cmd .ubuntu-venv/bin/python

if ! gh auth status >/dev/null 2>&1; then
  echo "GitHub CLI is not authenticated. Run: gh auth login" >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree is not clean. Commit/stash changes before release." >&2
  exit 1
fi

tag="v${version}"
branch="release/${tag}"

log "Fetching latest main"
git fetch origin main --prune
git switch main
git pull --ff-only origin main

if git rev-parse "${tag}" >/dev/null 2>&1 || git ls-remote --tags origin "${tag}" | grep -q "${tag}$"; then
  echo "Tag ${tag} already exists locally or on origin." >&2
  exit 1
fi

if git show-ref --verify --quiet "refs/heads/${branch}"; then
  echo "Local branch ${branch} already exists. Delete it or choose another version." >&2
  exit 1
fi

if git ls-remote --heads origin "${branch}" | grep -q "${branch}$"; then
  echo "Remote branch ${branch} already exists. Delete it or choose another version." >&2
  exit 1
fi

log "Creating release branch ${branch}"
git switch -c "${branch}"

log "Preparing version/changelog"
.ubuntu-venv/bin/python tools/release_prepare.py --version "${version}"

log "Running quality gates"
.ubuntu-venv/bin/python -m ruff check .
.ubuntu-venv/bin/python -m ruff format --check .
.ubuntu-venv/bin/python -m mypy src
.ubuntu-venv/bin/python -m pytest

git add src/tz_player/version.py CHANGELOG.md
if git diff --cached --quiet; then
  echo "No release changes detected after preparation." >&2
  exit 1
fi

log "Committing release metadata"
git commit -m "release: ${tag}"

log "Pushing release branch"
git push -u origin "${branch}"

log "Opening pull request"
pr_url="$(gh pr create \
  --base main \
  --head "${branch}" \
  --title "release: ${tag}" \
  --body "Automated release prep for ${tag}.")"
log "PR: ${pr_url}"

log "Waiting for PR checks to finish"
gh pr checks "${pr_url}" --watch --fail-fast

log "Merging PR"
gh pr merge "${pr_url}" --squash --delete-branch

log "Retrieving merge commit"
merge_sha="$(gh pr view "${pr_url}" --json mergeCommit --jq '.mergeCommit.oid')"
if [[ -z "${merge_sha}" || "${merge_sha}" == "null" ]]; then
  echo "Unable to determine merge commit SHA from PR ${pr_url}." >&2
  exit 1
fi

log "Refreshing main and creating tag ${tag}"
git fetch origin main --prune
git switch main
git pull --ff-only origin main
git tag -a "${tag}" "${merge_sha}" -m "Release ${tag}"

log "Pushing tag ${tag}"
git push origin "${tag}"

log "Done. Tag ${tag} pushed and GitHub Release workflow should start automatically."
