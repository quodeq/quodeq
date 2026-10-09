#!/usr/bin/env python3
"""Re-score stored dimension reports with the production grade formula and print the calibration yardsticks.

Usage:
    uv run python tools/grade_calibration.py <root>... [--classes compiled|proxy|none]
        [--params FILE] [--labels FILE] [--grid FILE] [--motion RUNID:REQ,REQ]

A root holds ``<project>/<run>/evaluation/<dimension>.json``. The table sets
the stored scores beside the current formula's. Output is numbers and short
project names only: no file path and no code snippet is ever printed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from _grade_calibration_load import load_reports  # noqa: E402
from _grade_calibration_metrics import (  # noqa: E402
    CLASS_MODES,
    GRADES,
    RUN_WIDTH,
    label_rows,
    resolve_classes,
    score_report,
    yardsticks,
)
from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams, params_from_dict  # noqa: E402

__all__ = ["main", "score_report"]

ENCODING = "utf-8"
MISSING = "-"
STORED_WIDTH = 58


def _fmt(value: object) -> str:
    return MISSING if value is None else f"{value:.2f}" if isinstance(value, float) else str(value)


def _range(value: list[float] | None) -> str:
    return MISSING if value is None else f"{value[0]:.1f} - {value[1]:.1f}"


def _shares(value: dict[str, float]) -> str:
    return " ".join(f"{g[:4]} {value[g]:.1f}%" for g in GRADES)


_ROWS = (
    ("reports", "reports", _fmt),
    ("mean score", "mean_score", _fmt),
    ("benchmark range", "benchmark_range", _range),
    ("benchmark deviation", "benchmark_deviation", _fmt),
    ("model pairs", "model_pairs", _fmt),
    ("model deviation", "model_deviation", _fmt),
    ("signal to noise", "signal_to_noise", _fmt),
    ("temporal pairs", "temporal_pairs", _fmt),
    ("temporal mean delta", "temporal_mean_delta", _fmt),
    ("temporal p90", "temporal_p90", _fmt),
    ("grade shares", "grade_shares", _shares),
)


def _print_table(stored: dict, current: dict) -> None:
    print(f"{'yardstick':<22}{'stored':<{STORED_WIDTH}}current")
    for title, key, fmt in _ROWS:
        print(f"{title:<22}{fmt(stored[key]):<{STORED_WIDTH}}{fmt(current[key])}")


def _print_motion(rows: list[dict]) -> None:
    for row in rows:
        change = "no findings left" if row["after"] is None else f"{row['after']:.1f} ({row['delta']:+.1f})"
        print(f"motion {row['project']} {row['dimension']} run {row['run']}: {row['before']:.1f} -> {change}")


def _print_labels(rows: list[dict]) -> None:
    for row in rows:
        verdict = "match" if row["match"] else "no match"
        print(f"label {row['project']}: {_fmt(row['score'])} {row['band']}, expected {row['expected']}: {verdict}")


def _read_json(path: str) -> object:
    return json.loads(Path(path).read_text(encoding=ENCODING))


def _parse_motion(raw: str | None) -> tuple[str, list[str]] | None:
    if not raw:
        return None
    run, _sep, rules = raw.partition(":")
    return run, [r for r in rules.split(",") if r]


def _scores(reports: list, params: ScoringParams, classes: dict[str, str]) -> list[float | None]:
    return [score_report(r, params, classes) for r in reports]


def _print_grid(reports: list, grid: list[dict], classes: dict[str, str]) -> None:
    for number, entry in enumerate(grid, 1):
        params = params_from_dict(entry)
        y = yardsticks(reports, _scores(reports, params, classes), params=params)
        print(f"grid {number}: bench {_range(y['benchmark_range'])} model dev {_fmt(y['model_deviation'])} "
              f"s/n {_fmt(y['signal_to_noise'])} temporal {_fmt(y['temporal_mean_delta'])} p90 {_fmt(y['temporal_p90'])} "
              f"| {_shares(y['grade_shares'])} | {json.dumps(entry, sort_keys=True)}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("roots", nargs="+", type=Path)
    parser.add_argument("--classes", choices=CLASS_MODES, default="compiled")
    parser.add_argument("--params", help="JSON file of formula params (camelCase), default the shipped formula")
    parser.add_argument("--labels", help='JSON {"<project>": "<grade>"} of expected bands')
    parser.add_argument("--grid", help="JSON list of param dicts, one yardstick row each")
    parser.add_argument("--motion", help="RUNID:REQ,REQ, the grade change when those rules' violations are removed")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the harness; returns the process exit code."""
    args = _parser().parse_args(argv)
    reports = load_reports([p.expanduser() for p in args.roots])
    params = params_from_dict(_read_json(args.params)) if args.params else DEFAULT_PARAMS
    classes = resolve_classes(args.classes, reports)
    scores = _scores(reports, params, classes)
    motion = _parse_motion(args.motion)
    stored = yardsticks(reports, [r.cur for r in reports])
    current = yardsticks(reports, scores, params=params, motion=motion, classes=classes)
    print(f"classes {args.classes} ({len(classes)} rules), run ids shown to {RUN_WIDTH} characters")
    _print_table(stored, current)
    _print_motion(current["motion"])
    if args.labels:
        _print_labels(label_rows(reports, scores, _read_json(args.labels), params))
    if args.grid:
        _print_grid(reports, _read_json(args.grid), classes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
