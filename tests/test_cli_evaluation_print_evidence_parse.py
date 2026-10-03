"""`print_scores` parses a dimension's evidence jsonl exactly once.

Sibling to test_cli_evaluation_print.py (already at the 240-line cap) rather
than an addition to it. A dismissal that matches the run's evidence used to
trigger two separate parses of the same jsonl file: one to count exclusions
(_count_excluded_findings), one to rescore (score_dimension_from_evidence).
Both now share the single parse in rescore_dimension_from_evidence.

Also covers the other half of that contract (finding 10): the print path
stops before scoring when no suppression matched this run, while the
dashboard path keeps scoring by default.
"""
from __future__ import annotations

import json

from quodeq.cli_evaluation import print_scores
from quodeq.analysis._report_io import write_dimension_report
from quodeq.core.evidence.parser import EvidenceContext, parse_jsonl_to_evidence
from quodeq.core.scoring.engine import score_evidence
from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.services.dismissed import dismiss_finding, dismissed_keys

DIM = "maintainability"
# Small source_file_count/files_read, same rationale as
# test_cli_evaluation_print.py: keeps evidence above the
# confidence-classification floor so a dismiss actually moves the score.
SFC, FILES_READ = 10, 5


def _ev_line(req, file, line, sev="major", t="violation", p="Modularity", vt="VT-COUPLING"):
    return {"schema_version": 1, "req": req, "t": t, "file": file, "line": line,
            "severity": sev, "w": "title", "reason": f"reason {req} {file} {line}",
            "vt": vt, "p": p, "d": DIM}


def _build_run(run_dir, dim, lines) -> str:
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


def test_print_scores_parses_evidence_once_per_dimension(tmp_path, monkeypatch):
    import quodeq._cli_scoring as _scoring_mod
    import quodeq.services.evidence_rescore as _rescore_mod

    project_dir = tmp_path / "proj"
    run_dir = project_dir / "run1"
    lines = [
        _ev_line("R-1", "a.kt", 10, sev="major", vt="VT-COUPLING"),
        _ev_line("R-2", "a.kt", 20, sev="critical", vt="VT-GODCLASS"),
        _ev_line("C-1", "a.kt", 1, t="compliance"),
    ]
    original_score = _build_run(run_dir, DIM, lines)

    dismiss_finding(project_dir, {"req": "R-2", "file": "a.kt", "line": 20})
    assert dismissed_keys(project_dir), "dismiss did not register"

    real_parse = _rescore_mod.parse_jsonl_to_evidence
    calls = {"n": 0}

    def counting_parse(*a, **kw):
        calls["n"] += 1
        return real_parse(*a, **kw)

    monkeypatch.setattr(_rescore_mod, "parse_jsonl_to_evidence", counting_parse)
    # Guarded: the fixed code removes _cli_scoring's own copy of this import.
    monkeypatch.setattr(_scoring_mod, "parse_jsonl_to_evidence", counting_parse,
                        raising=False)

    print_scores({DIM: original_score}, run_dir, project_dir, DEFAULT_PARAMS)

    assert calls["n"] == 1, "evidence must be parsed exactly once per dimension"


def _counting_score_evidence(monkeypatch) -> dict:
    """Spy on the scoring engine as evidence_rescore calls it."""
    import quodeq.services.evidence_rescore as _rescore_mod

    calls = {"n": 0}
    real_score = _rescore_mod.score_evidence

    def counting(*a, **kw):
        calls["n"] += 1
        return real_score(*a, **kw)

    monkeypatch.setattr(_rescore_mod, "score_evidence", counting)
    return calls


def _run_with_unmatched_dismissal(tmp_path) -> tuple:
    """A scored run plus a dismissal that matches nothing in its evidence."""
    project_dir = tmp_path / "proj"
    run_dir = project_dir / "run1"
    original_score = _build_run(run_dir, DIM, [
        _ev_line("R-1", "a.kt", 10, sev="major"),
        _ev_line("C-1", "a.kt", 1, t="compliance"),
    ])
    dismiss_finding(project_dir, {"req": "R-9", "file": "elsewhere.kt", "line": 99})
    assert dismissed_keys(project_dir), "dismiss did not register"
    return project_dir, run_dir, original_score


def test_print_scores_does_not_score_when_nothing_was_excluded(tmp_path, monkeypatch):
    """Finding 10: any dismissal on the project sent the print path through a
    full score_evidence per dimension, where the old flow stopped at count 0."""
    project_dir, run_dir, original_score = _run_with_unmatched_dismissal(tmp_path)
    calls = _counting_score_evidence(monkeypatch)

    print_scores({DIM: original_score}, run_dir, project_dir, DEFAULT_PARAMS)

    assert calls["n"] == 0, "the CLI scored a dimension with nothing excluded"


def test_dashboard_path_still_scores_when_nothing_was_excluded(tmp_path, monkeypatch):
    """The dashboard needs the score itself, so its caller keeps the default."""
    from quodeq.services.deleted import deleted_keys
    from quodeq.services.evidence_rescore import (
        EvidenceScoreRequest,
        score_dimension_from_evidence,
    )

    project_dir, run_dir, _ = _run_with_unmatched_dismissal(tmp_path)
    calls = _counting_score_evidence(monkeypatch)

    result = score_dimension_from_evidence(run_dir, DIM, EvidenceScoreRequest(
        dismissed=dismissed_keys(project_dir), deleted=deleted_keys(project_dir),
        source_file_count=SFC, files_read=FILES_READ, params=DEFAULT_PARAMS,
    ))

    assert calls["n"] == 1
    assert result is not None
