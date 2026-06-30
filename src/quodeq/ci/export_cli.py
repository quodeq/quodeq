# src/quodeq/ci/export_cli.py
"""CLI handler for the `quodeq export` subcommand."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _tool_version() -> str:
    from quodeq import __version__
    return __version__ or "0.0.0+dev"


def handle_export(args) -> int:
    """Handle `quodeq export <format>`. Returns an exit code."""
    if getattr(args, "export_format", None) != "sarif":
        print("Usage: quodeq export sarif --evaluation-dir DIR -o FILE", file=sys.stderr)
        return 1
    return _handle_sarif(args)


def _handle_sarif(args) -> int:
    from quodeq.ci.reporter import load_evaluation_reports
    from quodeq.ci.sarif import build_sarif

    evaluation_dir = Path(args.evaluation_dir)
    if not evaluation_dir.is_dir():
        print(f"Error: evaluation directory not found: {evaluation_dir}", file=sys.stderr)
        return 1

    reports = load_evaluation_reports(evaluation_dir)
    doc = build_sarif(
        reports,
        tool_version=_tool_version(),
        min_severity=getattr(args, "min_severity", None),
        include_snippets=getattr(args, "with_snippets", False),
    )

    out_path = Path(args.output)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"Error: could not write SARIF to {out_path}: {exc}", file=sys.stderr)
        return 1

    count = sum(len(r["results"]) for r in doc["runs"])
    print(f"Wrote {count} finding(s) to {out_path}")
    return 0
