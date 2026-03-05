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

## Release Steps (explicit sequence)

1. Choose the exact version string.
Use forms like `0.3.0`, `0.3.1`, or `0.4.0rc1`. Tag format is always `v<version>` (example: `v0.3.0`).

### Distribution behavior for native spectrum helper

- Release packages now include native helper binaries for Linux and Windows under `tz_player/binaries/...` so the helper can be used immediately after install.
- Users do not need a separate helper download step after installing the Python package.
- By default, analysis uses Python backends.
- To opt in to native helper analysis, set `TZ_PLAYER_USE_BUNDLED_NATIVE_SPECTRUM_HELPER=1` (for packaged helper binaries) or `TZ_PLAYER_NATIVE_SPECTRUM_HELPER_CMD` (custom command).

2. Run the one-command local release entrypoint from a clean `main`:

```bash
python tools/release.py 0.5.1
```

The command prints a deterministic follow-up block after the tag is pushed. The exact template is:

```bash
gh workflow run Release --ref main --field version=<VERSION_OR_TAG> --field prerelease=<true|false> --field sign_artifacts=false
```

Alternative equivalent entrypoints:

```bash
make release VERSION=0.5.1
./tools/release.sh 0.5.1
```

The local command is designed to do everything required on your machine before GitHub builds artifacts:

- update version/changelog from a single source (`src/tz_player/version.py`)
- run quality gates
- prepare release branch/PR, wait for merge, and push the release tag

What it intentionally does **not** do locally:

- build wheels/sdists or attach them to a GitHub release

Those package artifacts are always produced in GitHub by the `Release` workflow when the tag is pushed.

What `tools/release.py` does:
1. Validates clean git state and required tooling (`git`, `gh`, Python interpreter).
2. Runs `tools/release_prepare.py` to update `src/tz_player/version.py` and `CHANGELOG.md`.
3. Runs required quality gates: `ruff check`, `ruff format --check`, `mypy src`, `pytest`.
4. Creates/pushes a release branch and opens a PR to `main`.
5. Waits for PR checks, enables auto-merge, and waits for PR merge.
6. Creates/pushes tag `v<version>` on the merged commit.
7. Tag push triggers the `Release` GitHub workflow, which builds and uploads artifacts.
8. Workflow artifacts include: release notes (`RELEASE_NOTES.md`), `SHA256SUMS`, wheel/sdist, and Linux/Windows helper binaries per release policy.

3. Follow-up commands for GitHub release packaging:

```bash
# Wait for the Release workflow queue/runs for the pushed tag:
gh run list --workflow Release --limit 10 --json databaseId,name,status,conclusion

# Pick the relevant run ID above and stream logs:
gh run view <run-id> --log

# Confirm release exists and includes artifacts:
gh release view v0.5.1 --json name,url,tagName,isPrerelease,assets
```

4. If a rebuild is required (for example after a workflow fix) and the tag already exists:

```bash
gh workflow run Release --ref main --field version=v0.5.1 --field prerelease=false --field sign_artifacts=false
```

5. Verify outputs after success:
- Tag `v<version>` exists.
- GitHub release `v<version>` exists with artifacts attached.
- `CHANGELOG.md` includes a dated section for the released version.
- `CHANGELOG.md` has reset `Unreleased` headings.
 - Attached artifacts include Linux/Windows helper binaries, `SHA256SUMS`, and checks/metadata files.

6. Optional publish step:
If you publish to package indexes, do it only after the GitHub release is verified.

## Failure Handling

1. Script fails before PR creation:
Fix local/tooling issue and re-run `python tools/release.py <version>`.

2. Script reports `no checks reported`:
`release.py` continues and tries auto-merge. If auto-merge is unavailable, merge the PR manually in GitHub and proceed with release workflow dispatch.

3. Script fails to merge PR:
Merge manually (respecting repo rules), create/push tag `v<version>`, then continue.

4. Release exists but assets are missing/wrong:
Re-run workflow via `workflow_dispatch` and set `version` to the same existing tag version (`0.5.1` or `v0.5.1`), then it will upload/replace assets.

5. Tag already exists error:
This means that version was already used. Pick the next version and re-run.

6. Branch protection blocks automation:
If PR merge is blocked, resolve required approvals/checks and rerun with a new version.

## Notes

- Automated versioning is intentionally not used.
- You manually choose the version at release time.
- `tools/release.py` automates the release flow end to end.

## Release Recovery Flows

Use this section when the normal flow fails and you need to continue safely.

### A) PR checks are missing or `gh pr checks` returns “no checks reported”

This is now handled as a warning in `tools/release.py` and the script continues, then tries auto-merge.
If auto-merge is unavailable, manual merge is expected:

1. Open the PR URL printed by `release.py`.
2. Merge the PR manually in GitHub.
3. Continue release by rerunning the release workflow for the same version (see section B) below).

### B) GitHub workflow dispatch returns `Could not create workflow dispatch event`

Only use this when you are rebuilding an existing tag or re-running after workflow changes.

1. Verify the tag exists on origin:

```bash
git ls-remote --tags origin | rg "refs/tags/v<version>"
```

2. If tag exists and you need a full rebuild:

```bash
gh workflow run Release --ref main --field version=<VERSION> --field prerelease=false --field sign_artifacts=false
```

3. If dispatch continues to fail, use the GitHub UI **Run workflow** button on `Release` and provide the same fields.

### C) Workflow fails with `Tag vX.Y.Z not found`

This means the tag was not pushed before dispatch. `Release` is designed to run from a real tag.

1. Find the merged PR:

```bash
gh pr list --search "release: <VERSION>" --state merged --limit 1
```

2. If the tag is missing, tag the merged commit and push it:

```bash
git switch main
git pull --ff-only origin main
git tag -a <VERSION> <MERGE_SHA> -m "Release <VERSION>"
git push origin <VERSION>
```

3. Trigger `Release` after the tag is present:

```bash
gh workflow run Release --ref main --field version=<VERSION> --field prerelease=false --field sign_artifacts=false
```
