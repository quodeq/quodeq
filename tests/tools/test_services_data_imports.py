"""Ratchet: services reach data concretions only through services/wiring.py.

wiring.py is the composition root (see its docstring); ports.py carries the
Protocols. Every other services module importing ``quodeq.data.*`` (except
``quodeq.data.ports.*``) is listed below. Shrink-only: remove an entry when
you route that import through wiring, never add one.
"""
from __future__ import annotations

import ast
from pathlib import Path

_SERVICES = Path(__file__).resolve().parents[2] / "src" / "quodeq" / "services"
_ALLOWED_FILES = {"wiring.py", "ports.py"}

_BASELINE = frozenset({
    "_accumulated_data.py:quodeq.data.fs.report_parser.runs",
    "_accumulated_data.py:quodeq.data.fs.run_files",
    "_browse_entries.py:quodeq.data.fs.report_parser",
    "_browse_mixin.py:quodeq.data.fs.report_parser",
    "_dashboard_response.py:quodeq.data.fs.report_parser.runs",
    "_dashboard_stale.py:quodeq.data.fs.report_parser.runs",
    "_external_jobs.py:quodeq.data.fs.report_parser.external_pid",
    "_external_jobs.py:quodeq.data.sqlite",
    "_fs_discipline.py:quodeq.data.fs.report_parser.runs",
    "_fs_metadata.py:quodeq.data.fs.report_parser.runs",
    "_fs_metadata.py:quodeq.data.fs.standards_prefs",
    "_mutation_projection.py:quodeq.data.sqlite.findings_repository",
    "_post_run_hook.py:quodeq.data.projection.projector",
    "_run_discard.py:quodeq.data.cache_store.local",
    "_run_status_readers.py:quodeq.data.fs.dimensions_state_store",
    "_run_status_readers.py:quodeq.data.sqlite",
    "_violations_jsonl.py:quodeq.data.fs.standards_loader",
    "_violations_jsonl.py:quodeq.data.fs.stream_files",
    "cache.py:quodeq.data.fs.report_parser.runs",
    "cache.py:quodeq.data.fs.run_files",
    "cache_maintenance.py:quodeq.data.cache_store.local",
    "cache_maintenance.py:quodeq.data.cache_store.migrate",
    "dashboard_trend.py:quodeq.data.fs.report_parser.runs",
    "fs_project_helpers.py:quodeq.data.fs.report_parser.runs",
    "fs_scan.py:quodeq.data.fs.project_files",
    "fs_scan.py:quodeq.data.git_cli",
    "grade_formula.py:quodeq.data.fs.grade_formula_store",
    "grade_formula.py:quodeq.data.fs.run_status_store",
    "grade_formula.py:quodeq.data.projection.grade_projector",
    "grade_formula.py:quodeq.data.sqlite.state_store",
    "precedent_dismiss.py:quodeq.data.actions_log",
    "project_index.py:quodeq.data.fs.project_index",
    "run_keys.py:quodeq.data.sqlite.findings_queries",
    "run_reports.py:quodeq.data.fs.report_parser.runs",
    "runs_unit.py:quodeq.data.fs.report_parser.runs",
    "runs_unit.py:quodeq.data.sqlite.run_index",
    "score_run.py:quodeq.data.fs.standards_loader",
    "shared_repo.py:quodeq.data.fs.shared_repo",
    "standards_prefs.py:quodeq.data.fs.compiled_standards",
    "standards_prefs.py:quodeq.data.fs.standards_prefs",
    "trend_fetcher.py:quodeq.data.fs.report_parser.runs",
})


def _is_concrete(module: str) -> bool:
    return module.startswith("quodeq.data") and not module.startswith("quodeq.data.ports")


def _edges() -> set[str]:
    edges: set[str] = set()
    for path in sorted(_SERVICES.rglob("*.py")):
        rel = path.relative_to(_SERVICES).as_posix()
        if rel in _ALLOWED_FILES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and _is_concrete(node.module):
                edges.add(f"{rel}:{node.module}")
            elif isinstance(node, ast.Import):
                edges.update(f"{rel}:{a.name}" for a in node.names if _is_concrete(a.name))
    return edges


def test_no_new_services_to_data_edges():
    new = sorted(_edges() - _BASELINE)
    assert new == [], (
        "services modules must import data concretions via services/wiring.py:\n"
        + "\n".join(new)
    )


def test_baseline_has_no_stale_entries():
    stale = sorted(_BASELINE - _edges())
    assert stale == [], "Remove these fixed edges from _BASELINE:\n" + "\n".join(stale)
