# Release Runbook

This is the step-by-step process for cutting a `tz-player` release.

## Version Source of Truth

- Canonical version lives in `src/tz_player/version.py`.
- Packaging reads version dynamically from `pyproject.toml` (`tool.setuptools.dynamic.version`).
- Never manually edit version values in multiple files.

## One-Time Setup

1. Confirm GitHub Actions has permission to push to `main` and create tags.
2. Optional signing setup (only if you plan to sign artifacts): add `RELEASE_GPG_PRIVATE_KEY` (base64-encoded armored private key) and `RELEASE_GPG_PASSPHRASE` GitHub secrets.
3. Confirm workflow exists: `.github/workflows/release.yml`.

Optional key encoding helper:

```bash
base64 -w0 < private.key.asc
```

## Release Steps

1. Choose the exact version string.
Use forms like `0.3.0`, `0.3.1`, or `0.4.0rc1`. Tag format is always `v<version>` (example: `v0.3.0`).

2. Run local preflight checks from repo root:

```bash
.ubuntu-venv/bin/python -m ruff check .
.ubuntu-venv/bin/python -m ruff format --check .
.ubuntu-venv/bin/python -m mypy src
.ubuntu-venv/bin/python -m pytest
```

3. Open GitHub Actions and run workflow:
Go to `Actions` -> `Manual Release`, click `Run workflow`, then set:
- `version`: your chosen version (`0.5.1` and `v0.5.1` are both accepted).
- `prerelease`: `true` for release candidates, `false` for stable releases.
- `sign_artifacts`: `false` unless you have configured GPG secrets and want signatures.

4. Wait for the workflow to complete.
Workflow actions:
1. Runs `tools/release_prepare.py` to update `src/tz_player/version.py` and `CHANGELOG.md`.
2. Runs quality gates (`ruff`, `mypy`, `pytest`).
3. Builds artifacts and runs `twine check`.
4. Runs external-tooling guardrail scans (no bundled VLC/FFmpeg runtime binaries).
5. Generates `dist/SHA256SUMS`.
6. Optionally signs artifacts (`*.asc`) if `sign_artifacts=true`.
7. Commits release files, tags `v<version>`, pushes to `main`, publishes GitHub release.

5. Verify outputs after success:
- A commit exists on `main` with message `release: v<version>`.
- Tag `v<version>` exists.
- GitHub release `v<version>` exists with artifacts attached.
- `CHANGELOG.md` includes a dated section for the released version.
- `CHANGELOG.md` has reset `Unreleased` headings.

6. Optional publish step:
If you publish to package indexes, do it only after the GitHub release is verified.

## Failure Handling

1. Workflow fails before push/tag:
Fix the reported issue and re-run workflow with the same version.

2. Workflow fails after release commit pushed but before release publish:
Do not reuse a different version unless necessary. Re-run with the same version only if tag was not created. If tag was created but release publish failed, publish manually for that same tag.

3. Tag already exists error:
This means that version was already used. Pick the next version and re-run.

4. Branch protection blocks push:
Allow GitHub Actions bot to push release commits/tags, or perform the release commit/tag manually.

## Notes

- Automated versioning is intentionally not used.
- You manually choose the version at release time.
- The workflow automates everything else.
