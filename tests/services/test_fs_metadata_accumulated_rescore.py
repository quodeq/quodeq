"""Tests for _fs_metadata.py — run_dir_by_dim per-dimension source rescore.

Split from test_fs_metadata.py (further split out of
test_fs_metadata_accumulated.py to stay under the file-size cap). Pins
the `run_dir_by_dim` bookkeeping in `read_accumulated_summary`: on the
accumulated/project-card path, each dimension must be rescored from the
evidence of the run it was actually SOURCED from -- not unconditionally
from the newest run.
"""
from __future__ import annotations

import json
from unittest.mock import patch

from quodeq.core.run.state import RunState
from quodeq.services._fs_metadata import read_accumulated_summary


def _fsm_evidence_line(dim, req, file, line, sev="major", t="violation", p="Confidentiality", vt="VT-COUPLING"):
    """One evidence-jsonl judgment (same shape as test_evidence_rescore.py)."""
    return {"schema_version": 1, "req": req, "t": t, "file": file, "line": line,
            "severity": sev, "w": "title", "reason": f"reason {req} {file} {line}",
            "vt": vt, "p": p, "d": dim}


_RUN_OLD_ID, _RUN_NEW_ID = "20260101T000000", "20260102T000000"
_DIM_A, _DIM_B = "security", "reliability"
_SFC, _FILES_READ = 10, 5


def _write_evidence(ev_dir, dim, lines) -> None:
    """Write one dimension's evidence JSONL under *ev_dir*."""
    ev_dir.mkdir(parents=True, exist_ok=True)
    (ev_dir / f"{dim}_evidence.jsonl").write_text(
        "\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8",
    )


def _write_two_run_fixture(project_dir) -> None:
    """Two runs where each dimension's real evidence lives in a different one.

    Dimension A's spread across two principles lives in the OLDER run, so a
    dismissal actually moves its score (mirrors
    tests/services/test_dashboard_dismiss_consistency.py). Dimension B's
    lives only in the NEWER run. The newer run also carries a dimension-A
    file with completely unrelated content that the dismissal below does not
    match, so a regression that rescored A from the newest run would silently
    reflect that fabricated evidence instead of failing.
    """
    _write_evidence(project_dir / _RUN_OLD_ID / "evidence", _DIM_A, [
        _fsm_evidence_line(_DIM_A, "R-1", "a.kt", 10, sev="major", vt="VT-COUPLING"),
        _fsm_evidence_line(_DIM_A, "R-2", "a.kt", 20, sev="critical", vt="VT-GODCLASS"),
        _fsm_evidence_line(_DIM_A, "R-5", "b.kt", 7, sev="major", vt="VT-COUPLING"),
        _fsm_evidence_line(_DIM_A, "C-1", "a.kt", 1, t="compliance"),
        _fsm_evidence_line(_DIM_A, "C-3", "b.kt", 3, t="compliance"),
        _fsm_evidence_line(_DIM_A, "R-4", "c.kt", 9, sev="major", vt="VT-DUPLICATION", p="Integrity"),
        _fsm_evidence_line(_DIM_A, "C-2", "c.kt", 2, t="compliance", p="Integrity"),
    ])
    ev_dir_new = project_dir / _RUN_NEW_ID / "evidence"
    _write_evidence(ev_dir_new, _DIM_B, [
        _fsm_evidence_line(_DIM_B, "R-10", "x.kt", 3, sev="major", vt="VT-COUPLING", p="Availability"),
        _fsm_evidence_line(_DIM_B, "C-10", "x.kt", 1, t="compliance", p="Availability"),
    ])
    _write_evidence(ev_dir_new, _DIM_A, [
        _fsm_evidence_line(_DIM_A, "Z-1", "z.kt", 99, sev="minor", vt="VT-NAMING"),
    ])


def _per_run_scalars():
    """What read_run_data reports per run: A's last valid run is the older one."""
    from quodeq.core.types import DimensionResult
    from quodeq.core.types.finding import Finding

    def _viol(req, file, line, principle, severity, dim):
        return Finding(req=req, file=file, line=line, practice_id=principle,
                       severity=severity, dimension=dim)

    def _comp(req, file, line, principle, dim):
        return Finding(req=req, file=file, line=line, practice_id=principle, dimension=dim)

    return {
        _RUN_NEW_ID: [DimensionResult(
            dimension=_DIM_B, overall_score="7.0/10", overall_grade="B",
            files_read=_FILES_READ, source_file_count=_SFC,
            violations=[_viol("R-10", "x.kt", 3, "Availability", "major", _DIM_B)],
            compliance=[_comp("C-10", "x.kt", 1, "Availability", _DIM_B)],
        )],
        _RUN_OLD_ID: [DimensionResult(
            dimension=_DIM_A, overall_score="6.0/10", overall_grade="C",
            files_read=_FILES_READ, source_file_count=_SFC,
            violations=[
                _viol("R-1", "a.kt", 10, "Confidentiality", "major", _DIM_A),
                _viol("R-2", "a.kt", 20, "Confidentiality", "critical", _DIM_A),
                _viol("R-5", "b.kt", 7, "Confidentiality", "major", _DIM_A),
                _viol("R-4", "c.kt", 9, "Integrity", "major", _DIM_A),
            ],
            compliance=[
                _comp("C-1", "a.kt", 1, "Confidentiality", _DIM_A),
                _comp("C-3", "b.kt", 3, "Confidentiality", _DIM_A),
                _comp("C-2", "c.kt", 2, "Integrity", _DIM_A),
            ],
        )],
    }


def _rescore(run_dir, dismissed):
    """Dimension A's score from *run_dir*'s evidence, with *dismissed* applied."""
    from quodeq.core.scoring.params import DEFAULT_PARAMS
    from quodeq.services.evidence_rescore import EvidenceScoreRequest, score_dimension_from_evidence

    return score_dimension_from_evidence(
        run_dir, _DIM_A, EvidenceScoreRequest(
            dismissed=dismissed, deleted=set(),
            source_file_count=_SFC, files_read=_FILES_READ, params=DEFAULT_PARAMS,
        ),
    )


class TestPerDimensionRunDirRescore:
    """Pins the `run_dir_by_dim` bookkeeping in `read_accumulated_summary`: on
    the accumulated/project-card path, each dimension must be rescored from
    the evidence of the run it was actually SOURCED from -- not
    unconditionally from the newest run.
    """

    @patch("quodeq.services._fs_metadata.summarize_dimensions")
    @patch("quodeq.services._fs_metadata.read_run_data")
    def test_dimension_rescored_from_its_sourced_run_not_the_newest(
        self, mock_read, mock_summarize, tmp_path, monkeypatch,
    ):
        from quodeq.core.scoring.params import DEFAULT_PARAMS
        from quodeq.data.fs.report_parser.runs import RunInfo
        from quodeq.services.dismissed import dismiss_finding, dismissed_keys

        monkeypatch.setenv("QUODEQ_DISABLE_SCORE_CACHE", "1")
        reports_root = tmp_path / "evaluations"
        project = "proj-two-run"
        project_dir = reports_root / project
        _write_two_run_fixture(project_dir)

        per_run = _per_run_scalars()
        mock_read.side_effect = lambda root, proj, run_id: per_run[run_id]
        mock_summarize.return_value = type(
            "S", (), {"overall_grade": "B", "numeric_average": 6.5},
        )()

        # Dismiss a finding in dimension A (the older run) via the real
        # ActionLogWriter-backed path.
        dismiss_finding(project_dir, {"req": "R-2", "file": "a.kt", "line": 20})
        dismissed = dismissed_keys(project_dir)
        assert dismissed, "dismiss did not register"

        expected = _rescore(project_dir / _RUN_OLD_ID, dismissed)
        assert expected is not None and expected.overall.weighted_score is not None

        # The distinguishing fact: rescoring dim_a from the NEWER run's dir
        # (the wrong-run regression) produces a DIFFERENT, real score -- not
        # merely a missing-evidence None -- so a regression can't be masked
        # by a fallback path silently agreeing with the correct answer.
        wrong = _rescore(project_dir / _RUN_NEW_ID, dismissed)
        assert wrong is not None
        assert wrong.overall.weighted_score != expected.overall.weighted_score, (
            "fixture is not distinguishable: old-run and new-run rescores "
            "of dimension A must differ"
        )

        # Runs passed newest-first, exactly like the real list_runs() order.
        runs = [
            RunInfo(run_id=_RUN_NEW_ID, date_iso="2026-01-02", date_label="Jan 02", status=RunState.DONE),
            RunInfo(run_id=_RUN_OLD_ID, date_iso="2026-01-01", date_label="Jan 01", status=RunState.DONE),
        ]
        read_accumulated_summary(reports_root, project, runs, DEFAULT_PARAMS)

        acc_dims = mock_summarize.call_args[0][0]
        dim_a_result = next(d for d in acc_dims if d.dimension == _DIM_A)
        assert dim_a_result.overall_score == f"{expected.overall.weighted_score}/10", (
            "dimension A must be rescored from the OLDER run it was sourced "
            "from, not from the newest run_dir"
        )
