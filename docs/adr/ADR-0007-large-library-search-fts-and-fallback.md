# ADR-0007 Large-Library Playlist Search via SQLite FTS5 with Compatibility Fallback

- Status: Accepted
- Date: 2026-02-20

## Context

`tz-player` now targets very large playlists (for example 100k+ rows). The existing Find/search path performs tokenized `LIKE` matching across joined metadata/path fields. At this size, that approach becomes scan-heavy and can cause noticeable search latency under repeated queries.

The project still needs:
- deterministic behavior
- migration-safe persistence changes
- compatibility across environments where SQLite capabilities differ

## Decision

1. Introduce a migration-backed SQLite FTS5 playlist search index for Find/search workloads.
2. Keep `PlaylistStore.search_item_ids(...)` deterministic by:
   - using FTS5 when available
   - falling back to existing `LIKE` token matching when FTS5 is unavailable
3. Keep the FTS index synchronized through DB-level triggers tied to playlist, track path, and metadata mutations.
4. Include search-path mode (`fts` vs fallback) in observability fields for slow query diagnostics.

## Reasoning

- FTS5 is the most practical local improvement for text search latency at 100k+ scale in SQLite.
- A hard dependency on FTS5 would reduce portability; fallback preserves behavior on constrained SQLite builds.
- DB-level sync triggers avoid event-loop blocking and keep indexing logic centralized near persistence.
- Explicit observability supports tuning and regression detection without guessing which path executed.

## Consequences

### Positive

- Large-playlist search performance improves significantly on standard SQLite builds.
- Existing behavior remains available on non-FTS builds.
- Search indexing remains consistent through normal playlist/metadata operations.

### Tradeoffs

- Schema and trigger complexity increase.
- FTS tokenization semantics are not identical to arbitrary substring matching in every edge case.
- Trigger maintenance adds migration/test burden.

## Follow-up

- Expand opt-in perf checks with larger search stress cases and mode-aware assertions.
- Add documentation for search behavior differences between FTS and fallback modes.
- Reassess whether optional ranking/advanced query syntax should remain out of scope for v1.
