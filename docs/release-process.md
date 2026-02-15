# Release Runbook

This is the step-by-step process for cutting a `tz-player` release.

## Version Source of Truth

- Canonical version lives in `src/tz_player/version.py`.
- Packaging reads version dynamically from `pyproject.toml` (`tool.setuptools.dynamic.version`).
- Never manually edit version values in multiple files.

## One-Time Setup

1. Confirm GitHub Actions can create/edit GitHub releases.
2. Optional signing setup (only if you plan to sign artifacts): add `RELEASE_GPG_PRIVATE_KEY` (base64-encoded armored private key) and `RELEASE_GPG_PASSPHRASE` GitHub secrets.
3. Confirm workflow exists: `.github/workflows/release.yml`.

Optional key encoding helper:

```bash
base64 -w0 < private.key.asc
```

## Release Steps

1. Choose the exact version string.
Use forms like `0.3.0`, `0.3.1`, or `0.4.0rc1`. Tag format is always `v<version>` (example: `v0.3.0`).

2. Prepare release files on a branch:

```bash
.ubuntu-venv/bin/python tools/release_prepare.py --version 0.5.1 --notes-file RELEASE_NOTES.md
```

This updates:
- `src/tz_player/version.py`
- `CHANGELOG.md`

3. Open a PR with those changes and merge it using your normal repository rules (PR required, signed commits).

4. Run local preflight checks from repo root:

```bash
.ubuntu-venv/bin/python -m ruff check .
.ubuntu-venv/bin/python -m ruff format --check .
.ubuntu-venv/bin/python -m mypy src
.ubuntu-venv/bin/python -m pytest
```

5. Create and push the release tag from the merged main commit:

```bash
git checkout main
git pull
git tag -a v0.5.1 -m "Release v0.5.1"
git push origin v0.5.1
```

6. Wait for the `Release` workflow to complete.
Workflow actions:
1. Checks out the tagged commit.
2. Extracts release notes for that version from `CHANGELOG.md`.
3. Runs quality gates (`ruff`, `mypy`, `pytest`).
4. Builds artifacts and runs `twine check`.
5. Runs external-tooling guardrail scans (no bundled VLC/FFmpeg runtime binaries).
6. Generates `dist/SHA256SUMS`.
7. Optionally signs artifacts (`*.asc`) if `sign_artifacts=true`.
8. Creates or updates the GitHub release for that tag and uploads artifacts.

7. Verify outputs after success:
- Tag `v<version>` exists.
- GitHub release `v<version>` exists with artifacts attached.
- `CHANGELOG.md` includes a dated section for the released version.
- `CHANGELOG.md` has reset `Unreleased` headings.

8. Optional publish step:
If you publish to package indexes, do it only after the GitHub release is verified.

## Failure Handling

1. Workflow fails after tag push:
Fix the reported issue, push a fix in a new PR, then move to a new version/tag.

2. Release exists but assets are missing/wrong:
Re-run workflow via `workflow_dispatch` and set `version` to the same existing tag version (`0.5.1` or `v0.5.1`), then it will upload/replace assets.

3. Tag already exists error:
This means that version was already used. Pick the next version and re-run.

4. Branch protection blocks automation:
Expected. This workflow does not push to `main`; release file changes must happen through PR.

## Notes

- Automated versioning is intentionally not used.
- You manually choose the version at release time.
- The workflow automates everything else.
