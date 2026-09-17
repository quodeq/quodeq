"""`_print_scores` parses a dimension's evidence jsonl exactly once.

Sibling to test_cli_evaluation_print.py (already at the 240-line cap) rather
than an addition to it. A dismissal that matches the run's evidence used to
trigger two separate parses of the same jsonl file: one to count exclusions
(_count_excluded_findings), one to rescore (score_dimension_from_evidence).
Both now share the single parse in rescore_dimension_from_evidence.
"""
from __future__ import annotations

import json

from quodeq._cli_evaluation import _print_scores
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

    _print_scores({DIM: original_score}, run_dir, project_dir, DEFAULT_PARAMS)

    assert calls["n"] == 1, "evidence must be parsed exactly once per dimension"
