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

### Distribution behavior for native spectrum helper

- Release packages now include native helper binaries for Linux and Windows under `tz_player/binaries/...` so the helper can be used immediately after install.
- Users do not need to run a separate helper download step after installing the Python package.
- On first analysis run, the app attempts to use the packaged helper binaries when available; if not present or failing, it falls back to the Python-only analysis path.

2. Run the one-command local release entrypoint:

```bash
python tools/release.py 0.5.1
```

Alternative options:

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
# Wait for the Release workflow to finish for the new tag:
gh run list --workflow Release --branch v0.5.1 --limit 5

# View the workflow run and logs:
gh run list --workflow Release --limit 5 --json databaseId,name,status,conclusion
gh run view <run-id> --log

# Confirm release exists and includes artifacts:
gh release view v0.5.1 --json tagName,name,url --jq '.'
```

If a rebuild is required (for example after a workflow fix), run:

```bash
gh workflow run Release --field version=0.5.1 --field prerelease=false --field sign_artifacts=false
```

4. Verify outputs after success:
- Tag `v<version>` exists.
- GitHub release `v<version>` exists with artifacts attached.
- `CHANGELOG.md` includes a dated section for the released version.
- `CHANGELOG.md` has reset `Unreleased` headings.
 - Attached artifacts include `SHA256SUMS` and checks/metadata files.

5. Optional publish step:
If you publish to package indexes, do it only after the GitHub release is verified.

## Failure Handling

1. Script fails before PR creation:
Fix local/tooling issue and re-run `python tools/release.py <version>`.

2. Script fails waiting on PR checks:
Open the PR URL printed by the script, fix CI issues, and re-run the command with a new version.

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
