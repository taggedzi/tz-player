# ADR-0005 - External Media Tooling Policy and Doctor Diagnostics

- Status: Accepted
- Date: 2026-02-14
- Deciders: Project owner and implementation agent

## Context

`tz-player` uses VLC/libVLC for real playback and can use FFmpeg for optional non-WAV envelope analysis. The project is MIT-licensed and aims to keep distribution/licensing obligations simple and explicit for a small-scale release model.

Bundling external codec/media binaries inside project packages introduces additional compliance and distribution complexity. Users also need clear diagnostics when local media tooling is missing or partially configured.

## Decision

Adopt an external-only media tooling policy and add first-class diagnostics:

- VLC/libVLC and FFmpeg are user-installed external tools; `tz-player` does not bundle them in wheel/release artifacts.
- FFmpeg usage remains optional and capability-gated at runtime.
- When FFmpeg is unavailable, envelope analysis degrades safely to supported fallback paths (for example WAV/native and service fallback levels).
- Add a CLI diagnostics command (`tz-player doctor`) to report readiness for:
  - VLC/python-vlc/libVLC runtime availability
  - FFmpeg discoverability/version
  - metadata reader availability
- Diagnostics output must include actionable install guidance links/commands and meaningful exit codes.

## Consequences

Positive:

- Preserves MIT project licensing posture with lower distribution complexity.
- Avoids shipping third-party binaries in release artifacts.
- Improves user supportability with explicit environment diagnostics.
- Keeps optional features optional without blocking core playback/UX fallback behavior.

Negative:

- User environment setup requirements are higher for full feature coverage.
- Behavior can vary by local system tool availability.
- Documentation/support burden increases for installation troubleshooting.

## Alternatives Considered

- Bundle FFmpeg/VLC binaries directly with project artifacts.
  - Rejected due to licensing/distribution complexity and release maintenance burden.
- Require FFmpeg as a hard runtime dependency.
  - Rejected because core player functionality should remain usable without it.
- Keep tooling optional but provide no diagnostics command.
  - Rejected due to poor troubleshooting UX.

## Follow-up Work

- Implement runtime gating checks that enforce external-only FFmpeg/VLC usage.
- Implement `tz-player doctor` command and tests.
- Surface clear in-app/log diagnostics for missing FFmpeg in non-WAV envelope paths.
- Keep `docs/media-setup.md`, `docs/license-compliance.md`, and `THIRD_PARTY_LICENSES.md` aligned with this policy.
