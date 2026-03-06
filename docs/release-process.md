# Release Runbook

This runbook describes the production release path for `tz-player`.

## Goal

Use one local command to cut and publish a GitHub release with:

- version bump (`src/tz_player/version.py`)
- changelog section (`CHANGELOG.md`)
- annotated git tag (`v<version>`)
- release notes from changelog
- wheel/sdist artifacts
- Linux/Windows native helper artifacts
- `SHA256SUMS`
- optional GPG signatures

## One-Time Setup

1. Ensure GitHub Actions has `contents: write` permission.
2. If branch protection is enabled on `main`, allow the GitHub Actions bot to push release commits (ruleset bypass).
3. Optional signing setup: add repository secrets `RELEASE_GPG_PRIVATE_KEY` and `RELEASE_GPG_PASSPHRASE`.
4. Ensure these workflows exist:
- `.github/workflows/release-cut.yml`
- `.github/workflows/release.yml`

## Standard Release (Single Command)

From your local clone:

```bash
python tools/release.py 1.2.3
```

Equivalent helpers:

```bash
make release VERSION=1.2.3
tools\release.cmd 1.2.3
```

What this command does now:

1. Dispatches `Release Cut` workflow.
2. Streams workflow progress until completion.
3. Ends successfully only when release build/publish completes.

What `Release Cut` does in CI:

1. Runs `tools/release_prepare.py`.
2. Runs required quality gates (`ruff`, `mypy`, `pytest`).
3. Commits release metadata directly to `main`.
4. Creates and pushes tag `v<version>`.
5. Calls reusable `Release` workflow to build and publish artifacts.

## Useful Flags

```bash
python tools/release.py 1.2.3 --no-watch
python tools/release.py 1.3.0rc1 --prerelease
python tools/release.py 1.2.3 --sign-artifacts
python tools/release.py 1.2.3 --stable
```

## Rebuild Existing Tag Artifacts

If a tag already exists and you only need to rebuild/upload artifacts:

```bash
gh workflow run Release --ref main --field version=v1.2.3 --field force_rebuild=true --field prerelease=false --field sign_artifacts=false
```

## Verification

After success:

```bash
gh release view v1.2.3 --json name,url,tagName,isPrerelease,assets
git show v1.2.3 --no-patch --pretty=fuller
```

## Notes

- Existing releases are now updated with fresh `CHANGELOG.md` notes via `gh release edit` before artifact upload.
- This prevents stale/no-change text from previous release drafts or manually created releases.
