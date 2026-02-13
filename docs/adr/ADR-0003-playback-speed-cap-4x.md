# ADR-0003 - Cap Playback Speed at 4.0x

- Status: Accepted
- Date: 2026-02-13
- Deciders: Project owner and implementation agent

## Context

`tz-player` exposes playback speed controls via keyboard and slider input. In practice, VLC backend playback at speeds above `4.0x` has shown silent audio behavior, which creates a confusing UX: the app reports playback progress, but users hear no audio.

The previous speed cap (`8.0x`) allowed users to enter a range where backend behavior is unreliable.

## Decision

Set a project-wide playback speed range of `0.5x` to `4.0x`:

- Clamp `PlayerService` speed changes and direct speed sets to `<= 4.0x`.
- Clamp status-pane speed slider mapping to a `4.0x` max.
- Clamp fake backend speed to the same limit for behavioral consistency in tests.
- Clamp persisted startup speed when converting app state to runtime player state.

## Consequences

Positive:

- Avoids silent-audio states observed with VLC at higher rates.
- Keeps keyboard, slider, and persisted-state behavior consistent.
- Improves predictability for users and test environments.

Negative:

- Removes access to `> 4.0x` playback for users who might accept backend tradeoffs.
- Existing persisted states with higher speed values are normalized down to `4.0x` at runtime.

## Alternatives Considered

- Keep `8.0x` maximum and only warn users when audio may fail.
- Make speed max backend-specific at runtime (higher complexity and UX branching).

## Follow-up Work

- If future backend evidence supports reliable audio above `4.0x`, revisit with backend-specific capability negotiation.
- Keep docs and tests aligned with speed bounds.
