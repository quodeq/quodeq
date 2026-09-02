"""Tests for quodeq.services.dashboard — SQL grade overlay contract.

Split from test_dashboard.py (further split out of test_dashboard_build.py
to stay under the file-size cap): dashboard scores come from CLI
evaluation JSON, no SQL overlay -- except once the SQL projector and the
CLI engine agree on the same confidence-level rule, in which case the
overlay surfaces the SQL-baked grade.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from quodeq.services.dashboard import build_dashboard


class TestDashboardSqlOverlayAfterConfidenceFix:
    """The SQL grade overlay is back, but only after the SQL projector and
    the CLI engine were unified on the same confidence-level rule (see
    ``core.evidence.model.classify_confidence_level``).  These tests pin
    the new contract: when SQL grade tables are populated, the dashboard
    surfaces them — which is now safe because they're computed with the
    same formula the CLI used to write the evaluation JSON.

    Previous incarnation of these tests (``TestDashboardSqlGradeOverride``)
    pinned the same overlay against the buggy projector formula; that
    behaviour caused the 7.7-vs-9.0 dashboard-vs-CLI split the user
    reported.  Now that both engines agree, the overlay is a feature
    (live updates on dismiss) rather than a divergence.
    """

    @staticmethod
    def _write_eval_json(
        run_dir: Path, dimension: str, score: str, grade: str,
    ) -> None:
        """Write a minimal eval JSON so read_run_data parses one dimension."""
        eval_dir = run_dir / "evaluation"
        eval_dir.mkdir(parents=True, exist_ok=True)
        (eval_dir / f"{dimension}.json").write_text(json.dumps({
            "schema_version": 1,
            "dimension": dimension,
            "project": "r",
            "discipline": "Python",
            "date": "2026-05-23",
            "sourceFileCount": 100,
            "overallScore": score,
            "overallGrade": grade,
            "principles": [],
            "violations": [],
            "compliance": [],
            "totals": {"violationCount": 0, "complianceCount": 0, "severity": {}},
        }), encoding="utf-8")

    def test_dashboard_overlays_sql_grades_when_populated(self, tmp_path: Path) -> None:
        """SQL grade tables override the stale eval-time FS grade.

        The overlay now lives inside ``read_run_data`` (so every consumer
        agrees), so this test exercises the real reader against a run whose
        SQL grade tables were baked by the projector (events + recompute)
        and whose eval JSON carries a different, stale grade.
        """
        from quodeq.core.events.models import Judgment
        from quodeq.core.scoring.params import DEFAULT_PARAMS
        from quodeq.data.fs.report_parser import RunInfo as _RI
        from quodeq.data.projection.grade_projector import recompute_grades
        from quodeq.data.sqlite.state_store import SQLiteStateStore
        from quodeq.services.dashboard import clear_shared_dimension_cache

        clear_shared_dimension_cache()
        project = "myproject"
        run_id = "r1"
        run_dir = tmp_path / project / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "events.jsonl").write_text("")  # marks an event-log run

        # Bake real SQL grades from findings (mirrors the projector flow).
        store = SQLiteStateStore(run_dir)
        for i in range(6):
            store.record_finding(Judgment(
                practice_id="p1", dimension="security", req=f"req{i}",
                verdict="violation", severity="major", file=f"f{i}.py", line=1,
                title=f"t{i}", reason=f"r{i}",
            ))
        for i in range(8):
            store.record_finding(Judgment(
                practice_id="p1", dimension="security", req=f"c{i}",
                verdict="compliance", severity="minor", file=f"g{i}.py", line=1,
                title=f"ct{i}", reason=f"cr{i}",
            ))
        store.save_projected_size((run_dir / "events.jsonl").stat().st_size)
        recompute_grades(run_dir, params=DEFAULT_PARAMS)
        sql_rows = {r["dimension"]: r for r in store.read_dimension_scores()}
        baked = sql_rows["security"]
        assert baked["grade"] is not None

        # The eval JSON carries a deliberately different (stale) grade.
        self._write_eval_json(run_dir, "security", "2.0/10", "Critical")

        with patch(
            "quodeq.services.dashboard.list_runs",
            return_value=[_RI(run_id=run_id, date_iso="2024-01-01", date_label="2024-01-01")],
        ):
            result = build_dashboard(str(tmp_path), project, run_id)

        clear_shared_dimension_cache()
        sec = result["dimensions"][0]
        # Overlay wins: the SQL-baked grade, not the stale "Critical".
        assert sec["overallGrade"] == baked["grade"]
        assert sec["overallScore"] == f"{baked['score']}/10"
        assert sec["overallGrade"] != "Critical"
        # The run-level summary is derived from the overlaid dims.
        assert result["summary"]["overallGrade"] == baked["grade"]

    def test_dashboard_falls_back_to_fs_when_sql_tables_empty(
        self, tmp_path: Path,
    ) -> None:
        """No SQL rows → use FS grade unchanged (this is the steady state
        for runs that haven't been projected, e.g. legacy runs without
        events.jsonl)."""
        from quodeq.data.fs.report_parser import RunInfo as _RI
        from quodeq.services.dashboard import clear_shared_dimension_cache

        clear_shared_dimension_cache()
        project = "myproject"
        run_id = "r1"
        run_dir = tmp_path / project / run_id
        run_dir.mkdir(parents=True)
        # No events.jsonl → legacy run, overlay must be a no-op.
        self._write_eval_json(run_dir, "security", "7.7/10", "Good")

        with patch(
            "quodeq.services.dashboard.list_runs",
            return_value=[_RI(run_id=run_id, date_iso="2024-01-01", date_label="2024-01-01")],
        ):
            result = build_dashboard(str(tmp_path), project, run_id)

        clear_shared_dimension_cache()
        sec = result["dimensions"][0]
        assert sec["overallScore"] == "7.7/10"
        assert sec["overallGrade"] == "Good"
