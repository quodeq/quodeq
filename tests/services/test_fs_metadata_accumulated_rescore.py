"""Tests for _fs_metadata.py — run_dir_by_dim per-dimension source rescore.

Split from test_fs_metadata.py (further split out of
test_fs_metadata_accumulated.py to stay under the file-size cap). Pins
the `run_dir_by_dim` bookkeeping in `_read_accumulated_summary`
(services/_fs_metadata.py:98-142): on the accumulated/project-card path,
each dimension must be rescored from the evidence of the run it was
actually SOURCED from -- not unconditionally from the newest run.
"""
from __future__ import annotations

import json
from unittest.mock import patch

from quodeq.services._fs_metadata import _read_accumulated_summary


def _fsm_evidence_line(dim, req, file, line, sev="major", t="violation", p="Confidentiality", vt="VT-COUPLING"):
    """One evidence-jsonl judgment (same shape as test_evidence_rescore.py)."""
    return {"schema_version": 1, "req": req, "t": t, "file": file, "line": line,
            "severity": sev, "w": "title", "reason": f"reason {req} {file} {line}",
            "vt": vt, "p": p, "d": dim}


class TestPerDimensionRunDirRescore:
    """Pins the `run_dir_by_dim` bookkeeping in `_read_accumulated_summary`
    (services/_fs_metadata.py:98-142): on the accumulated/project-card path,
    each dimension must be rescored from the evidence of the run it was
    actually SOURCED from -- not unconditionally from the newest run.
    """

    @patch("quodeq.services._fs_metadata.summarize_dimensions")
    @patch("quodeq.services._fs_metadata.read_run_data")
    def test_dimension_rescored_from_its_sourced_run_not_the_newest(
        self, mock_read, mock_summarize, tmp_path, monkeypatch,
    ):
        from quodeq.core.scoring.params import DEFAULT_PARAMS
        from quodeq.core.types import DimensionResult
        from quodeq.core.types.finding import Finding
        from quodeq.data.fs.report_parser.runs import RunInfo
        from quodeq.services.dismissed import dismiss_finding, dismissed_keys
        from quodeq.services.evidence_rescore import score_dimension_from_evidence

        monkeypatch.setenv("QUODEQ_DISABLE_SCORE_CACHE", "1")
        reports_root = tmp_path / "evaluations"
        project = "proj-two-run"
        run_old_id, run_new_id = "20260101T000000", "20260102T000000"
        project_dir = reports_root / project
        run_old_dir = project_dir / run_old_id
        run_new_dir = project_dir / run_new_id
        dim_a, dim_b = "security", "reliability"
        sfc, files_read = 10, 5

        # --- dimension A's real evidence lives in the OLDER run: a spread
        # across two principles so a dismissal actually moves the score
        # (mirrors tests/services/test_dashboard_dismiss_consistency.py). ---
        ev_dir_old = run_old_dir / "evidence"
        ev_dir_old.mkdir(parents=True)
        (ev_dir_old / f"{dim_a}_evidence.jsonl").write_text(
            "\n".join(json.dumps(l) for l in [
                _fsm_evidence_line(dim_a, "R-1", "a.kt", 10, sev="major", vt="VT-COUPLING"),
                _fsm_evidence_line(dim_a, "R-2", "a.kt", 20, sev="critical", vt="VT-GODCLASS"),
                _fsm_evidence_line(dim_a, "R-5", "b.kt", 7, sev="major", vt="VT-COUPLING"),
                _fsm_evidence_line(dim_a, "C-1", "a.kt", 1, t="compliance"),
                _fsm_evidence_line(dim_a, "C-3", "b.kt", 3, t="compliance"),
                _fsm_evidence_line(dim_a, "R-4", "c.kt", 9, sev="major", vt="VT-DUPLICATION", p="Integrity"),
                _fsm_evidence_line(dim_a, "C-2", "c.kt", 2, t="compliance", p="Integrity"),
            ]) + "\n", encoding="utf-8",
        )

        # --- dimension B's real evidence lives ONLY in the NEWER run. ---
        ev_dir_new = run_new_dir / "evidence"
        ev_dir_new.mkdir(parents=True)
        (ev_dir_new / f"{dim_b}_evidence.jsonl").write_text(
            "\n".join(json.dumps(l) for l in [
                _fsm_evidence_line(dim_b, "R-10", "x.kt", 3, sev="major", vt="VT-COUPLING", p="Availability"),
                _fsm_evidence_line(dim_b, "C-10", "x.kt", 1, t="compliance", p="Availability"),
            ]) + "\n", encoding="utf-8",
        )

        # The newer run ALSO has evidence for dimension A's filename, but with
        # completely different, unrelated content (none of it matches the
        # dismissal below) -- so if a regression used this dir for dimension A,
        # the dismiss would be a no-op and the rescore would silently reflect
        # this fabricated evidence's own (very different) score instead of the
        # real sourced run's.
        (ev_dir_new / f"{dim_a}_evidence.jsonl").write_text(
            "\n".join(json.dumps(l) for l in [
                _fsm_evidence_line(dim_a, "Z-1", "z.kt", 99, sev="minor", vt="VT-NAMING"),
            ]) + "\n", encoding="utf-8",
        )

        # Scalars read_run_data would report for each run: dim_a's "last
        # valid" occurrence is the OLDER run; dim_b's is the NEWER run.
        per_run = {
            run_new_id: [DimensionResult(
                dimension=dim_b, overall_score="7.0/10", overall_grade="B",
                files_read=files_read, source_file_count=sfc,
                violations=[Finding(req="R-10", file="x.kt", line=3,
                                     practice_id="Availability", severity="major",
                                     dimension=dim_b)],
                compliance=[Finding(req="C-10", file="x.kt", line=1,
                                    practice_id="Availability", dimension=dim_b)],
            )],
            run_old_id: [DimensionResult(
                dimension=dim_a, overall_score="6.0/10", overall_grade="C",
                files_read=files_read, source_file_count=sfc,
                violations=[
                    Finding(req="R-1", file="a.kt", line=10,
                            practice_id="Confidentiality", severity="major", dimension=dim_a),
                    Finding(req="R-2", file="a.kt", line=20,
                            practice_id="Confidentiality", severity="critical", dimension=dim_a),
                    Finding(req="R-5", file="b.kt", line=7,
                            practice_id="Confidentiality", severity="major", dimension=dim_a),
                    Finding(req="R-4", file="c.kt", line=9,
                            practice_id="Integrity", severity="major", dimension=dim_a),
                ],
                compliance=[
                    Finding(req="C-1", file="a.kt", line=1,
                            practice_id="Confidentiality", dimension=dim_a),
                    Finding(req="C-3", file="b.kt", line=3,
                            practice_id="Confidentiality", dimension=dim_a),
                    Finding(req="C-2", file="c.kt", line=2,
                            practice_id="Integrity", dimension=dim_a),
                ],
            )],
        }
        mock_read.side_effect = lambda root, proj, run_id: per_run[run_id]
        mock_summarize.return_value = type(
            "S", (), {"overall_grade": "B", "numeric_average": 6.5},
        )()

        # Dismiss a finding in dimension A (the older run) via the real
        # ActionLogWriter-backed path.
        dismiss_finding(project_dir, {"req": "R-2", "file": "a.kt", "line": 20})
        dismissed = dismissed_keys(project_dir)
        assert dismissed, "dismiss did not register"

        expected = score_dimension_from_evidence(
            run_old_dir, dim_a, dismissed=dismissed, deleted=set(),
            source_file_count=sfc, files_read=files_read, params=DEFAULT_PARAMS,
        )
        assert expected is not None
        assert expected.overall.weighted_score is not None

        # The distinguishing fact: rescoring dim_a from the NEWER run's dir
        # (the wrong-run regression) produces a DIFFERENT, real score -- not
        # merely a missing-evidence None -- so a regression can't be masked
        # by a fallback path silently agreeing with the correct answer.
        wrong = score_dimension_from_evidence(
            run_new_dir, dim_a, dismissed=dismissed, deleted=set(),
            source_file_count=sfc, files_read=files_read, params=DEFAULT_PARAMS,
        )
        assert wrong is not None
        assert wrong.overall.weighted_score != expected.overall.weighted_score, (
            "fixture is not distinguishable: old-run and new-run rescores "
            "of dimension A must differ"
        )

        # Runs passed newest-first, exactly like the real list_runs() order.
        runs = [
            RunInfo(run_id=run_new_id, date_iso="2026-01-02", date_label="Jan 02", status="complete"),
            RunInfo(run_id=run_old_id, date_iso="2026-01-01", date_label="Jan 01", status="complete"),
        ]
        _read_accumulated_summary(reports_root, project, runs, DEFAULT_PARAMS)

        acc_dims = mock_summarize.call_args[0][0]
        dim_a_result = next(d for d in acc_dims if d.dimension == dim_a)
        assert dim_a_result.overall_score == f"{expected.overall.weighted_score}/10", (
            "dimension A must be rescored from the OLDER run it was sourced "
            "from, not from the newest run_dir"
        )
