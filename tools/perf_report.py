"""Generate a simple HTML report for perf suite summary artifacts."""

from __future__ import annotations

import argparse
import html
import json
import webbrowser
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from statistics import fmean
from typing import Any

from tz_player.perf_benchmarking import compare_perf_run_payloads, load_perf_run_payload


@dataclass(frozen=True)
class SuiteArtifactEntry:
    path: Path
    file_name: str
    created_at: str
    run_id: str
    scenario_key: str
    payload: dict[str, Any]


def _analysis_zero_tracks_warning(payload: dict[str, Any]) -> str | None:
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list):
        return None
    affected: list[str] = []
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            continue
        scenario_id = scenario.get("scenario_id")
        counters = scenario.get("counters")
        if not isinstance(counters, dict):
            continue
        analyzed = counters.get("tracks_analyzed")
        requested = counters.get("tracks_requested")
        if (
            isinstance(analyzed, int)
            and isinstance(requested, int)
            and requested > 0
            and analyzed == 0
            and isinstance(scenario_id, str)
            and scenario_id
        ):
            affected.append(scenario_id)
    if not affected:
        return None
    return "zero_tracks_analyzed=" + ",".join(sorted(affected))


def _analysis_backend_summary(payload: dict[str, Any]) -> str:
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list):
        return "n/a"
    backend_counts: dict[str, int] = {}
    beat_backend_counts: dict[str, int] = {}
    waveform_backend_counts: dict[str, int] = {}
    fallback_counts: dict[str, int] = {}
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            continue
        metadata = scenario.get("metadata")
        if not isinstance(metadata, dict):
            continue
        raw_backend_counts = metadata.get("analysis_backend_counts")
        if isinstance(raw_backend_counts, dict):
            for key, value in raw_backend_counts.items():
                if isinstance(key, str) and isinstance(value, int):
                    backend_counts[key] = backend_counts.get(key, 0) + value
        raw_beat_backend_counts = metadata.get("beat_backend_counts")
        if isinstance(raw_beat_backend_counts, dict):
            for key, value in raw_beat_backend_counts.items():
                if isinstance(key, str) and isinstance(value, int):
                    beat_backend_counts[key] = beat_backend_counts.get(key, 0) + value
        raw_waveform_backend_counts = metadata.get("waveform_proxy_backend_counts")
        if isinstance(raw_waveform_backend_counts, dict):
            for key, value in raw_waveform_backend_counts.items():
                if isinstance(key, str) and isinstance(value, int):
                    waveform_backend_counts[key] = (
                        waveform_backend_counts.get(key, 0) + value
                    )
        raw_fallback_counts = metadata.get("analysis_fallback_reason_counts")
        if isinstance(raw_fallback_counts, dict):
            for key, value in raw_fallback_counts.items():
                if isinstance(key, str) and isinstance(value, int):
                    fallback_counts[key] = fallback_counts.get(key, 0) + value
    if (
        not backend_counts
        and not beat_backend_counts
        and not waveform_backend_counts
        and not fallback_counts
    ):
        return "n/a"
    parts: list[str] = []
    if backend_counts:
        parts.append(
            "backends="
            + ",".join(f"{key}:{backend_counts[key]}" for key in sorted(backend_counts))
        )
    if beat_backend_counts:
        parts.append(
            "beat="
            + ",".join(
                f"{key}:{beat_backend_counts[key]}"
                for key in sorted(beat_backend_counts)
            )
        )
    if waveform_backend_counts:
        parts.append(
            "waveform="
            + ",".join(
                f"{key}:{waveform_backend_counts[key]}"
                for key in sorted(waveform_backend_counts)
            )
        )
    if fallback_counts:
        parts.append(
            "fallbacks="
            + ",".join(
                f"{key}:{fallback_counts[key]}" for key in sorted(fallback_counts)
            )
        )
    return " ".join(parts)


def _native_helper_meta_summary(payload: dict[str, Any]) -> str:
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list):
        return "n/a"
    versions: set[str] = set()
    helper_cmds: set[str] = set()
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            continue
        metadata = scenario.get("metadata")
        if not isinstance(metadata, dict):
            continue
        helper_cmd = metadata.get("native_helper_cmd")
        if isinstance(helper_cmd, str) and helper_cmd:
            helper_cmds.add(helper_cmd)
        tracks = metadata.get("tracks")
        if isinstance(tracks, list):
            for track in tracks:
                if isinstance(track, dict):
                    version = track.get("native_helper_version")
                    if isinstance(version, str) and version:
                        versions.add(version)
    parts: list[str] = []
    if versions:
        parts.append("versions=" + ",".join(sorted(versions)))
    if helper_cmds:
        parts.append("cmd=" + " | ".join(sorted(helper_cmds)))
    return " ".join(parts) if parts else "n/a"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite_summary", type=Path, help="Perf suite summary JSON")
    parser.add_argument(
        "--compare-suite",
        type=Path,
        help="Optional candidate suite summary JSON for comparison mode",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output HTML path (default: alongside suite summary)",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        dest="open_report",
        help="Open generated report in the default browser (best effort).",
    )
    parser.add_argument(
        "--max-metrics",
        type=int,
        default=18,
        help="Max metrics shown per scenario group table (default: 18).",
    )
    parser.add_argument(
        "--regression-pct",
        type=float,
        default=5.0,
        help="Comparison regression threshold percent (default: 5.0).",
    )
    parser.add_argument(
        "--improvement-pct",
        type=float,
        default=-5.0,
        help="Comparison improvement threshold percent (default: -5.0).",
    )
    return parser.parse_args()


def _resolve_artifact_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if path.exists():
        return path.resolve()
    if ":" in raw_path and "\\" in raw_path:
        win = PureWindowsPath(raw_path)
        anchor = win.anchor.rstrip("\\/")
        if len(anchor) >= 2 and anchor[1] == ":":
            drive = anchor[0].lower()
            tail_parts = [part for part in win.parts[1:] if part not in {"\\", "/"}]
            wsl_path = Path("/mnt") / drive
            for part in tail_parts:
                wsl_path /= part
            if wsl_path.exists():
                return wsl_path.resolve()
    return path.resolve()


def _load_suite_summary(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"suite summary must be object: {path}")
    if payload.get("schema") != "tz_player.perf_run_suite_summary.v1":
        raise ValueError(f"unsupported suite summary schema: {path}")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError(f"suite summary missing artifacts list: {path}")
    return payload


def _scenario_signature(run_payload: dict[str, Any]) -> str:
    scenarios = run_payload.get("scenarios")
    if not isinstance(scenarios, list):
        return "unknown"
    pairs: list[str] = []
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            continue
        sid = scenario.get("scenario_id")
        category = scenario.get("category")
        if isinstance(sid, str) and sid:
            cat = category if isinstance(category, str) and category else "unknown"
            pairs.append(f"{cat}:{sid}")
    if not pairs:
        return "unknown"
    return "+".join(sorted(pairs))


def _load_suite_artifacts(summary: dict[str, Any]) -> list[SuiteArtifactEntry]:
    entries: list[SuiteArtifactEntry] = []
    for raw_path in summary.get("artifacts", []):
        if not isinstance(raw_path, str):
            continue
        path = _resolve_artifact_path(raw_path)
        payload = load_perf_run_payload(path)
        entries.append(
            SuiteArtifactEntry(
                path=path,
                file_name=path.name,
                created_at=str(payload.get("created_at") or ""),
                run_id=str(payload.get("run_id") or path.stem),
                scenario_key=_scenario_signature(payload),
                payload=payload,
            )
        )
    return sorted(entries, key=lambda e: (e.scenario_key, e.created_at, e.run_id))


def _escape(value: object) -> str:
    return html.escape(str(value))


def _fmt_num(value: float, *, digits: int = 3) -> str:
    abs_val = abs(value)
    if abs_val >= 1000:
        return f"{value:,.1f}"
    if abs_val >= 100:
        return f"{value:.1f}"
    if abs_val >= 10:
        return f"{value:.2f}"
    return f"{value:.{digits}f}"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.1f}%"


def _bytes_human(value: int | float | None) -> str:
    if value is None:
        return "n/a"
    n = float(value)
    units = ["B", "KB", "MB", "GB", "TB"]
    unit = units[0]
    for unit in units:
        if n < 1024 or unit == units[-1]:
            break
        n /= 1024.0
    return f"{n:.1f} {unit}"


def _group_entries(
    entries: list[SuiteArtifactEntry],
) -> dict[str, list[SuiteArtifactEntry]]:
    grouped: dict[str, list[SuiteArtifactEntry]] = {}
    for entry in entries:
        grouped.setdefault(entry.scenario_key, []).append(entry)
    return grouped


def _flatten_metrics(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    metrics: dict[str, dict[str, Any]] = {}
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list):
        return metrics
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            continue
        sid = scenario.get("scenario_id")
        cat = scenario.get("category")
        raw_metrics = scenario.get("metrics")
        if not isinstance(sid, str) or not isinstance(raw_metrics, dict):
            continue
        cat_str = cat if isinstance(cat, str) and cat else "unknown"
        for metric_name, metric in raw_metrics.items():
            if isinstance(metric_name, str) and isinstance(metric, dict):
                metrics[f"{cat_str}:{sid}.{metric_name}"] = metric
    return metrics


def _aggregate_group_metrics(
    entries: list[SuiteArtifactEntry], *, max_metrics: int
) -> list[dict[str, Any]]:
    collected: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        for key, metric in _flatten_metrics(entry.payload).items():
            collected.setdefault(key, []).append(metric)

    rows: list[dict[str, Any]] = []
    for key, samples in collected.items():
        unit = str(samples[0].get("unit") or "")
        medians = [float(s.get("median_value", 0.0)) for s in samples]
        p95s = [float(s.get("p95_value", 0.0)) for s in samples]
        maxima = [float(s.get("max_value", 0.0)) for s in samples]
        rows.append(
            {
                "metric_key": key,
                "unit": unit,
                "repeat_count": len(samples),
                "median_avg": fmean(medians),
                "median_min": min(medians),
                "median_max": max(medians),
                "p95_avg": fmean(p95s),
                "max_avg": fmean(maxima),
            }
        )
    rows.sort(key=lambda r: (r["unit"], -float(r["median_avg"]), r["metric_key"]))
    return rows[: max(1, max_metrics)]


def _metric_bar(value: float, max_value: float) -> str:
    pct = 0.0 if max_value <= 0 else max(0.0, min(100.0, (value / max_value) * 100.0))
    return (
        '<div class="bar"><div class="fill" style="width:'
        + f"{pct:.1f}%"
        + '"></div></div>'
    )


def _render_suite_overview(summary: dict[str, Any]) -> str:
    media_manifest = summary.get("media_manifest")
    media_tracks = None
    media_bytes = None
    if isinstance(media_manifest, dict):
        media_tracks = media_manifest.get("track_count")
        media_bytes = media_manifest.get("total_bytes")
    cards = [
        ("Run ID", summary.get("run_id", "")),
        ("Status", summary.get("status", "")),
        ("Created", summary.get("created_at", "")),
        ("Artifacts", summary.get("new_artifact_count", 0)),
        ("Repeat", summary.get("repeat", 1)),
        ("Media Tracks", media_tracks if media_tracks is not None else "n/a"),
        (
            "Media Size",
            _bytes_human(
                media_bytes if isinstance(media_bytes, (int, float)) else None
            ),
        ),
    ]
    html_cards = "".join(
        f'<div class="card"><div class="label">{_escape(label)}</div>'
        f'<div class="value">{_escape(value)}</div></div>'
        for label, value in cards
    )
    return f'<section><h2>Overview</h2><div class="cards">{html_cards}</div></section>'


def _render_group_table(
    group_key: str, entries: list[SuiteArtifactEntry], *, max_metrics: int
) -> str:
    rows = _aggregate_group_metrics(entries, max_metrics=max_metrics)
    max_median = max((float(r["median_avg"]) for r in rows), default=0.0)
    entry_rows = "".join(
        "<tr>"
        f"<td>{idx + 1}</td>"
        f"<td>{_escape(entry.file_name)}</td>"
        f"<td>{_escape(entry.run_id)}</td>"
        f"<td>{_escape(entry.created_at)}</td>"
        f"<td>{_escape(len(entry.payload.get('scenarios', [])))}</td>"
        f"<td>{_escape(_analysis_backend_summary(entry.payload))}</td>"
        f"<td>{_escape(_native_helper_meta_summary(entry.payload))}</td>"
        f"<td>{_escape(_analysis_zero_tracks_warning(entry.payload) or '')}</td>"
        "</tr>"
        for idx, entry in enumerate(entries)
    )
    metric_rows = "".join(
        "<tr>"
        f"<td>{_escape(r['metric_key'])}</td>"
        f"<td>{_escape(r['unit'])}</td>"
        f"<td>{r['repeat_count']}</td>"
        f"<td>{_fmt_num(float(r['median_avg']))}</td>"
        f"<td>{_fmt_num(float(r['p95_avg']))}</td>"
        f"<td>{_fmt_num(float(r['max_avg']))}</td>"
        f"<td>{_fmt_num(float(r['median_min']))} .. {_fmt_num(float(r['median_max']))}</td>"
        f"<td>{_metric_bar(float(r['median_avg']), max_median)}</td>"
        "</tr>"
        for r in rows
    )
    no_metrics_row = "<tr><td colspan='8'>No metrics</td></tr>"
    metric_tbody = metric_rows or no_metrics_row
    return (
        f'<section class="group"><h3>{_escape(group_key)}</h3>'
        "<details><summary>Artifacts / repeats</summary>"
        "<table><thead><tr><th>#</th><th>Artifact</th><th>Run ID</th><th>Created</th><th>Scenarios</th><th>Backend Meta</th><th>Helper Meta</th><th>Warnings</th></tr></thead>"
        f"<tbody>{entry_rows}</tbody></table></details>"
        "<table><thead><tr><th>Metric</th><th>Unit</th><th>Repeats</th><th>Median avg</th><th>P95 avg</th><th>Max avg</th><th>Median range</th><th>Bar</th></tr></thead>"
        f"<tbody>{metric_tbody}</tbody></table>"
        "</section>"
    )


def _pair_groups(
    base: dict[str, list[SuiteArtifactEntry]],
    cand: dict[str, list[SuiteArtifactEntry]],
) -> tuple[list[tuple[str, int, SuiteArtifactEntry, SuiteArtifactEntry]], list[str]]:
    all_keys = sorted(set(base) | set(cand))
    pairs: list[tuple[str, int, SuiteArtifactEntry, SuiteArtifactEntry]] = []
    mismatches: list[str] = []
    for key in all_keys:
        a = base.get(key, [])
        b = cand.get(key, [])
        if len(a) != len(b):
            mismatches.append(
                f"{key}: baseline_count={len(a)} candidate_count={len(b)}"
            )
        for idx in range(min(len(a), len(b))):
            pairs.append((key, idx + 1, a[idx], b[idx]))
    return pairs, mismatches


def _render_compare_section(
    baseline_summary: dict[str, Any],
    candidate_summary: dict[str, Any],
    baseline_entries: list[SuiteArtifactEntry],
    candidate_entries: list[SuiteArtifactEntry],
    *,
    regression_pct: float,
    improvement_pct: float,
) -> str:
    base_groups = _group_entries(baseline_entries)
    cand_groups = _group_entries(candidate_entries)
    pairs, mismatches = _pair_groups(base_groups, cand_groups)

    sections: list[str] = []
    total_reg = 0
    total_imp = 0
    for group_key, pair_index, base_entry, cand_entry in pairs:
        comp = compare_perf_run_payloads(
            base_entry.payload,
            cand_entry.payload,
            regression_pct_threshold=regression_pct,
            improvement_pct_threshold=improvement_pct,
        )
        total_reg += len(comp.regressed_metrics)
        total_imp += len(comp.improved_metrics)
        top_reg = comp.regressed_metrics[:5]
        top_imp = comp.improved_metrics[:5]
        reg_rows = "".join(
            "<tr>"
            f"<td>{_escape(item.scenario_id + '.' + item.metric_name)}</td>"
            f"<td>{_escape(item.unit)}</td>"
            f"<td>{_fmt_num(item.baseline_median)}</td>"
            f"<td>{_fmt_num(item.candidate_median)}</td>"
            f"<td class='bad'>{_fmt_pct(item.pct_median)}</td>"
            "</tr>"
            for item in top_reg
        )
        imp_rows = "".join(
            "<tr>"
            f"<td>{_escape(item.scenario_id + '.' + item.metric_name)}</td>"
            f"<td>{_escape(item.unit)}</td>"
            f"<td>{_fmt_num(item.baseline_median)}</td>"
            f"<td>{_fmt_num(item.candidate_median)}</td>"
            f"<td class='good'>{_fmt_pct(item.pct_median)}</td>"
            "</tr>"
            for item in top_imp
        )
        no_rows = "<tr><td colspan='5'>None</td></tr>"
        reg_tbody = reg_rows or no_rows
        imp_tbody = imp_rows or no_rows
        sections.append(
            "<section class='group'>"
            f"<h3>{_escape(group_key)} (pair {pair_index})</h3>"
            f"<p class='muted'>baseline={_escape(base_entry.file_name)} | candidate={_escape(cand_entry.file_name)}</p>"
            f"<p class='muted'>baseline backend: {_escape(_analysis_backend_summary(base_entry.payload))}</p>"
            f"<p class='muted'>candidate backend: {_escape(_analysis_backend_summary(cand_entry.payload))}</p>"
            f"<p class='muted'>baseline helper: {_escape(_native_helper_meta_summary(base_entry.payload))}</p>"
            f"<p class='muted'>candidate helper: {_escape(_native_helper_meta_summary(cand_entry.payload))}</p>"
            f"<p class='muted'>baseline warnings: {_escape(_analysis_zero_tracks_warning(base_entry.payload) or 'none')}</p>"
            f"<p class='muted'>candidate warnings: {_escape(_analysis_zero_tracks_warning(cand_entry.payload) or 'none')}</p>"
            "<table><thead><tr><th colspan='5'>Top Regressions</th></tr>"
            "<tr><th>Metric</th><th>Unit</th><th>Base median</th><th>Cand median</th><th>Delta %</th></tr></thead>"
            f"<tbody>{reg_tbody}</tbody></table>"
            "<table><thead><tr><th colspan='5'>Top Improvements</th></tr>"
            "<tr><th>Metric</th><th>Unit</th><th>Base median</th><th>Cand median</th><th>Delta %</th></tr></thead>"
            f"<tbody>{imp_tbody}</tbody></table>"
            "</section>"
        )

    mismatch_html = ""
    if mismatches:
        mismatch_html = (
            "<section><h2>Pairing Mismatches</h2><ul>"
            + "".join(f"<li>{_escape(item)}</li>" for item in mismatches)
            + "</ul></section>"
        )
    summary_cards = "".join(
        [
            f'<div class="card"><div class="label">Baseline run</div><div class="value">{_escape(baseline_summary.get("run_id"))}</div></div>',
            f'<div class="card"><div class="label">Candidate run</div><div class="value">{_escape(candidate_summary.get("run_id"))}</div></div>',
            f'<div class="card"><div class="label">Paired artifacts</div><div class="value">{len(pairs)}</div></div>',
            f'<div class="card"><div class="label">Regressions</div><div class="value bad">{total_reg}</div></div>',
            f'<div class="card"><div class="label">Improvements</div><div class="value good">{total_imp}</div></div>',
            f'<div class="card"><div class="label">Mismatches</div><div class="value">{len(mismatches)}</div></div>',
        ]
    )
    return (
        "<section><h2>Comparison Summary</h2>"
        f"<div class='cards'>{summary_cards}</div></section>"
        + mismatch_html
        + "".join(sections)
    )


def _render_html(
    suite_path: Path,
    summary: dict[str, Any],
    entries: list[SuiteArtifactEntry],
    *,
    compare_suite_path: Path | None = None,
    compare_summary: dict[str, Any] | None = None,
    compare_entries: list[SuiteArtifactEntry] | None = None,
    max_metrics: int,
    regression_pct: float,
    improvement_pct: float,
) -> str:
    title = f"tz-player Perf Report: {summary.get('run_id', suite_path.name)}"
    group_sections = "".join(
        _render_group_table(group_key, group_entries, max_metrics=max_metrics)
        for group_key, group_entries in sorted(_group_entries(entries).items())
    )
    compare_html = ""
    if (
        compare_suite_path is not None
        and compare_summary is not None
        and compare_entries is not None
    ):
        compare_html = _render_compare_section(
            summary,
            compare_summary,
            entries,
            compare_entries,
            regression_pct=regression_pct,
            improvement_pct=improvement_pct,
        )
    selected_scenarios = summary.get("selected_scenarios") or []
    scenarios_html = "".join(
        f"<li>{_escape(item)}</li>"
        for item in selected_scenarios
        if isinstance(item, str)
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{_escape(title)}</title>
  <style>
    :root {{
      --bg: #f7f5ef;
      --panel: #fffdf7;
      --ink: #1e1b16;
      --muted: #6f6a61;
      --line: #ddd5c7;
      --accent: #2f6f62;
      --bad: #b73c3c;
      --good: #2f7f3b;
      --bar: #d9d2c4;
      --fill: #2f6f62;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font: 14px/1.4 ui-sans-serif, system-ui, sans-serif; background: var(--bg); color: var(--ink); }}
    .wrap {{ max-width: 1400px; margin: 0 auto; padding: 16px; }}
    h1,h2,h3 {{ margin: 0 0 8px; line-height: 1.2; }}
    h1 {{ font-size: 22px; }}
    h2 {{ font-size: 17px; margin-top: 20px; }}
    h3 {{ font-size: 15px; margin-top: 16px; }}
    .muted {{ color: var(--muted); margin: 0 0 8px; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; margin-bottom: 12px; }}
    .card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 10px; }}
    .label {{ color: var(--muted); font-size: 12px; }}
    .value {{ font-size: 15px; font-weight: 600; word-break: break-word; }}
    .value.bad, .bad {{ color: var(--bad); }}
    .value.good, .good {{ color: var(--good); }}
    section.group {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 12px; margin: 12px 0; }}
    table {{ width: 100%; border-collapse: collapse; margin: 8px 0 12px; font-size: 12px; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 6px 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f3efe4; position: sticky; top: 0; }}
    td:nth-child(n+3) {{ white-space: nowrap; }}
    .bar {{ width: 140px; max-width: 100%; height: 9px; background: var(--bar); border-radius: 99px; overflow: hidden; }}
    .fill {{ height: 100%; background: linear-gradient(90deg, #6fb4a4, var(--fill)); }}
    details > summary {{ cursor: pointer; color: var(--accent); margin-bottom: 8px; }}
    ul {{ margin: 0; padding-left: 18px; }}
    .pilllist {{ display: flex; flex-wrap: wrap; gap: 6px; padding: 0; list-style: none; }}
    .pilllist li {{ background: #efe8da; border: 1px solid var(--line); border-radius: 999px; padding: 4px 8px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>{_escape(title)}</h1>
    <p class="muted">Suite summary: {_escape(suite_path.resolve())}</p>
    {_render_suite_overview(summary)}
    <section>
      <h2>Suite Selection</h2>
      <p class="muted">Selected suites: {_escape(", ".join(summary.get("selected_suites", [])))}</p>
      <ul class="pilllist">{scenarios_html}</ul>
    </section>
    {compare_html}
    <section><h2>Scenario Groups</h2>{group_sections}</section>
  </div>
</body>
</html>
"""


def main() -> int:
    args = _parse_args()
    suite_path = args.suite_summary.resolve()
    summary = _load_suite_summary(suite_path)
    entries = _load_suite_artifacts(summary)

    compare_path = args.compare_suite.resolve() if args.compare_suite else None
    compare_summary = _load_suite_summary(compare_path) if compare_path else None
    compare_entries = (
        _load_suite_artifacts(compare_summary) if compare_summary else None
    )

    output_path = (
        args.output.resolve()
        if args.output
        else suite_path.with_suffix(".report.html").resolve()
    )
    html_text = _render_html(
        suite_path,
        summary,
        entries,
        compare_suite_path=compare_path,
        compare_summary=compare_summary,
        compare_entries=compare_entries,
        max_metrics=max(1, int(args.max_metrics)),
        regression_pct=float(args.regression_pct),
        improvement_pct=float(args.improvement_pct),
    )
    output_path.write_text(html_text, encoding="utf-8")
    print(f"Wrote perf report: {output_path}")
    if args.open_report:
        try:
            opened = webbrowser.open(output_path.resolve().as_uri())
            print(
                f"Open report requested: {'ok' if opened else 'browser returned false'}"
            )
        except Exception as exc:
            print(f"Open report failed (non-fatal): {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
