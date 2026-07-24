"""`_print_scores` prints suppression-adjusted scores after a scan.

Covers the target behaviour: with no active dismissals/deletions, output is
byte-identical to the historical `  {dim}: {score}` line; when a dismissal
matches a just-scanned run's evidence, the evidence-based rescore is printed
instead with a `(N dismissed findings excluded)` suffix; a dimension whose
evidence is missing from the run falls back to the original line.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq._cli_evaluation import _print_scores
from quodeq.analysis._report_io import write_dimension_report
from quodeq.core.evidence.parser import EvidenceContext, parse_jsonl_to_evidence
from quodeq.core.scoring.engine import score_evidence
from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.services.dismissed import dismiss_finding, dismissed_keys
from quodeq.services.evidence_rescore import score_dimension_from_evidence

DIM = "maintainability"
# Small source_file_count/files_read (matching tests/services/test_evidence_rescore.py
# and tests/services/test_dashboard_dismiss_consistency.py) keeps this fixture's
# evidence count above the confidence-classification floor in
# core/evidence/model.py:classify_confidence_level -- at a large scale the
# principles read as "low" confidence and deductions are unconditionally
# zeroed, which would make a dismiss-changes-the-score assertion pass
# vacuously regardless of whether the exclusion actually took effect.
SFC, FILES_READ = 10, 5


def _ev_line(req, file, line, sev="major", t="violation", p="Modularity", vt="VT-COUPLING"):
    """One evidence-jsonl judgment (same shape as tests/services/test_evidence_rescore.py)."""
    return {"schema_version": 1, "req": req, "t": t, "file": file, "line": line,
            "severity": sev, "w": "title", "reason": f"reason {req} {file} {line}",
            "vt": vt, "p": p, "d": DIM}


def _build_run(run_dir: Path, dim: str, lines: list[dict]) -> str:
    """Write real evidence + a real scored report for *dim* via the actual
    scoring pipeline (score_evidence + write_dimension_report), so the
    written report's score matches evidence-based rescoring by construction.
    Returns the score string exactly as `run_full` would have produced it.
    """
    ev_dir = run_dir / "evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)
    jsonl = ev_dir / f"{dim}_evidence.jsonl"
    jsonl.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    evidence = parse_jsonl_to_evidence(jsonl, EvidenceContext(
        language=dim, repository="proj", date_str="2026-01-01",
        source_file_count=SFC, files_read=FILES_READ,
    ))
    scores = score_evidence(evidence, mode="numerical", params=DEFAULT_PARAMS)
    write_dimension_report(evidence, scores, dim, run_dir / "evaluation")
    return f"{scores.overall.weighted_score}/10"


def test_dismissal_prints_adjusted_score_with_suffix(tmp_path, capsys):
    project_dir = tmp_path / "proj"
    run_dir = project_dir / "run1"
    lines = [
        _ev_line("R-1", "a.kt", 10, sev="major", vt="VT-COUPLING"),
        _ev_line("R-2", "a.kt", 20, sev="critical", vt="VT-GODCLASS"),
        _ev_line("R-5", "b.kt", 7, sev="major", vt="VT-COUPLING"),
        _ev_line("C-1", "a.kt", 1, t="compliance"),
        _ev_line("C-3", "b.kt", 3, t="compliance"),
    ]
    original_score = _build_run(run_dir, DIM, lines)

    dismiss_finding(project_dir, {"req": "R-2", "file": "a.kt", "line": 20})
    dismissed = dismissed_keys(project_dir)
    assert dismissed, "dismiss did not register"

    expected = score_dimension_from_evidence(
        run_dir, DIM, dismissed=dismissed, deleted=set(),
        source_file_count=SFC, files_read=FILES_READ, params=DEFAULT_PARAMS,
    )
    assert expected is not None and expected.overall.weighted_score is not None
    # Sanity: the dismiss must actually move the score, or this test would
    # pass vacuously even if suppression exclusion were broken.
    assert f"{expected.overall.weighted_score}/10" != original_score

    _print_scores({DIM: original_score}, run_dir, project_dir, DEFAULT_PARAMS)

    out = capsys.readouterr().out
    assert out == f"  {DIM}: {expected.overall.weighted_score}/10 (1 dismissed findings excluded)\n"


def test_no_suppressions_prints_byte_identical_line(tmp_path, capsys):
    project_dir = tmp_path / "proj"
    run_dir = project_dir / "run1"
    lines = [
        _ev_line("R-1", "a.kt", 10),
        _ev_line("C-1", "a.kt", 1, t="compliance"),
    ]
    score = _build_run(run_dir, DIM, lines)

    _print_scores({DIM: score}, run_dir, project_dir, DEFAULT_PARAMS)

    out = capsys.readouterr().out
    assert out == f"  {DIM}: {score}\n"


def test_dimension_without_evidence_falls_back_to_original_line(tmp_path, capsys):
    """A dismissal is on record for the project (targeting some other
    dimension's finding), but this run has no evidence at all for
    "security" -- must fall back to the stored score, unchanged.
    """
    project_dir = tmp_path / "proj"
    run_dir = project_dir / "run1"
    run_dir.mkdir(parents=True)

    dismiss_finding(project_dir, {"req": "R-9", "file": "z.kt", "line": 1})
    assert dismissed_keys(project_dir), "dismiss did not register"

    _print_scores({"security": "8.0/10"}, run_dir, project_dir, DEFAULT_PARAMS)

    out = capsys.readouterr().out
    assert out == "  security: 8.0/10\n"
