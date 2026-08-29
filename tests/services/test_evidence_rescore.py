"""Evidence-based rescore reproduces scan-time scoring exactly."""
import json
from pathlib import Path

import pytest

from quodeq.core.evidence.parser import EvidenceContext, parse_jsonl_to_evidence
from quodeq.data.fs.standards_loader import read_req_to_principle_map
from quodeq.core.scoring.engine import score_evidence
from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.services.evidence_rescore import score_dimension_from_evidence

DIM = "maintainability"


def _write_evidence(run_dir: Path, lines: list[dict]) -> Path:
    ev_dir = run_dir / "evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)
    p = ev_dir / f"{DIM}_evidence.jsonl"
    p.write_text("\n".join(json.dumps(l) for l in lines) + "\n")
    return p


def _line(req, file, line, sev="major", t="violation", p="Modularity", vt="VT-COUPLING"):
    return {"schema_version": 1, "req": req, "t": t, "file": file, "line": line,
            "severity": sev, "w": "title", "reason": f"reason {req} {file} {line}",
            "vt": vt, "p": p, "d": DIM}


@pytest.fixture
def run_dir(tmp_path):
    lines = [
        _line("R-1", "a.kt", 10),
        _line("R-2", "a.kt", 20, sev="critical", vt="VT-GODCLASS"),
        _line("R-3", "b.kt", 5, sev="minor", vt=""),          # untyped -> reason fallback
        _line("C-1", "a.kt", 1, t="compliance"),
        _line("C-2", "c.kt", 2, t="compliance", p="Reusability"),
        _line("R-4", "c.kt", 9, p="Reusability"),
    ]
    _write_evidence(tmp_path, lines)
    return tmp_path


def test_zero_exclusions_matches_scan_time_scoring(run_dir):
    scan = score_evidence(
        parse_jsonl_to_evidence(
            run_dir / "evidence" / f"{DIM}_evidence.jsonl",
            EvidenceContext(language="", repository="", date_str="",
                            source_file_count=1000, files_read=50),
        ),
        mode="numerical", params=DEFAULT_PARAMS,
    )
    rescored = score_dimension_from_evidence(
        run_dir, DIM, dismissed=set(), deleted=set(),
        source_file_count=1000, files_read=50, params=DEFAULT_PARAMS,
    )
    assert rescored is not None
    assert rescored.overall.weighted_score == scan.overall.weighted_score
    assert {k: v.final_score for k, v in rescored.principles.items()} == \
           {k: v.final_score for k, v in scan.principles.items()}


def test_dismissed_key_removes_only_that_judgment(run_dir):
    # source_file_count=10 (vs. the 1000 used for the golden test above) keeps
    # this small fixture's evidence count above the confidence-classification
    # floor in core/evidence/model.py:classify_confidence_level -- at scale
    # 1000 Modularity's 4 instances read as "low" confidence and deductions
    # are unconditionally zeroed, which would make this assertion pass
    # vacuously regardless of whether dismissal actually filtered anything.
    base = score_dimension_from_evidence(
        run_dir, DIM, dismissed=set(), deleted=set(),
        source_file_count=10, files_read=5, params=DEFAULT_PARAMS)
    out = score_dimension_from_evidence(
        run_dir, DIM, dismissed={("R-2", "a.kt", 20)}, deleted=set(),
        source_file_count=10, files_read=5, params=DEFAULT_PARAMS)
    # The critical violation is gone from Modularity's tallies.
    assert out.principles["Modularity"].deductions.critical_type_count \
        == base.principles["Modularity"].deductions.critical_type_count - 1


def test_deleted_key_removes_principle_file_matches(run_dir):
    # Same confidence-floor reasoning as above: source_file_count=10 keeps
    # Reusability's 2 instances out of the "low confidence -> zeroed
    # deductions" bucket so the before/after comparison is meaningful.
    base = score_dimension_from_evidence(
        run_dir, DIM, dismissed=set(), deleted=set(),
        source_file_count=10, files_read=5, params=DEFAULT_PARAMS)
    out = score_dimension_from_evidence(
        run_dir, DIM, dismissed=set(),
        deleted={(DIM, "Reusability", "c.kt")},
        source_file_count=10, files_read=5, params=DEFAULT_PARAMS)
    # R-4 (violation, Reusability, c.kt) is present before deletion...
    assert base.principles["Reusability"].deductions.major_type_count == 1
    # ...and gone after; compliance C-2 stays, leaving no violation types.
    assert out.principles["Reusability"].deductions.major_type_count == 0


def test_quarantined_findings_stay_excluded_from_rescore(tmp_path, monkeypatch):
    """Scan time quarantines findings whose principle is not in the dimension's
    standard. The rescore must resolve the same standard and quarantine them
    too, otherwise a dismiss makes previously excluded findings re-enter the
    grade and phantom principles appear in the payload.
    """
    monkeypatch.setenv("QUODEQ_EVALUATORS_DIR", str(tmp_path / "no-evals"))
    lines = [
        _line("M-MOD-1", "a.kt", 10, p="Modularity"),
        _line("M-MOD-2", "a.kt", 1, t="compliance", p="Modularity"),
        # Off-standard principle: quarantined at scan time.
        _line("X-1", "z.kt", 3, sev="critical", p="NotInStandard"),
    ]
    _write_evidence(tmp_path, lines)

    from quodeq.config.paths import default_paths
    scan = score_evidence(
        parse_jsonl_to_evidence(
            tmp_path / "evidence" / f"{DIM}_evidence.jsonl",
            EvidenceContext(language="", repository="", date_str="",
                            source_file_count=10, files_read=5),
            compiled_dir=default_paths().standards_dir / "compiled",
            evaluators_dir=default_paths().evaluators_dir,
            req_map_reader=read_req_to_principle_map,
        ),
        mode="numerical", params=DEFAULT_PARAMS,
    )
    assert "NotInStandard" not in scan.principles  # fixture sanity

    rescored = score_dimension_from_evidence(
        tmp_path, DIM, dismissed=set(), deleted=set(),
        source_file_count=10, files_read=5, params=DEFAULT_PARAMS,
    )
    assert rescored is not None
    assert "NotInStandard" not in rescored.principles
    assert rescored.overall.weighted_score == scan.overall.weighted_score


@pytest.mark.parametrize("bad", ["../secret", "a/b", "..\\x", "x\0y"])
def test_traversal_dim_id_rejected_before_filesystem_access(tmp_path, bad):
    # dim_id builds a filesystem path; separators/traversal must be refused
    # rather than reaching Path.is_file()/stat() (py/path-injection guard).
    with pytest.raises(ValueError):
        score_dimension_from_evidence(
            tmp_path, bad, dismissed=set(), deleted=set(),
            source_file_count=0, files_read=0, params=DEFAULT_PARAMS)


def test_missing_or_empty_evidence_returns_none(tmp_path):
    assert score_dimension_from_evidence(
        tmp_path, DIM, dismissed=set(), deleted=set(),
        source_file_count=0, files_read=0, params=DEFAULT_PARAMS) is None
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence" / f"{DIM}_evidence.jsonl").write_text("")
    assert score_dimension_from_evidence(
        tmp_path, DIM, dismissed=set(), deleted=set(),
        source_file_count=0, files_read=0, params=DEFAULT_PARAMS) is None


def test_traversal_dim_id_does_not_read_evidence_planted_outside_run_dir(tmp_path):
    """A path-traversal dim_id must be rejected before the join, not silently
    walked outside run_dir -- CodeQL py/path-injection sink guard.

    Plants real evidence at the exact location the traversal would resolve
    to, so this test fails (proves a real read happened) if the guard is
    ever removed, instead of passing vacuously because the target is
    missing.
    """
    run_dir = tmp_path / "run"
    (run_dir / "evidence").mkdir(parents=True)
    secret_dir = tmp_path / "secret"
    secret_dir.mkdir()
    (secret_dir / "leak_evidence.jsonl").write_text(
        json.dumps(_line("R-1", "a.kt", 10)) + "\n"
    )
    traversal_dim_id = "../../secret/leak"
    # Sanity check: confirm the naive (unguarded) join really would resolve
    # onto the planted secret file, so this test actually exercises escape.
    escaped = run_dir / "evidence" / f"{traversal_dim_id}_evidence.jsonl"
    assert escaped.resolve() == (secret_dir / "leak_evidence.jsonl").resolve()

    # The guard raises before the join, so the planted secret is never read.
    with pytest.raises(ValueError):
        score_dimension_from_evidence(
            run_dir, traversal_dim_id, dismissed=set(), deleted=set(),
            source_file_count=1000, files_read=50, params=DEFAULT_PARAMS,
        )


def test_scoring_engine_exception_returns_none_for_fallback(run_dir, monkeypatch):
    """The engine can throw on edge-case evidence (see da04c1a2). The rescore
    must degrade to None (callers fall back to the stored/legacy score) rather
    than propagate and 500 the dashboard or /api/rescore for the whole run.
    """
    def _boom(*args, **kwargs):
        raise RuntimeError("scoring engine exploded")
    monkeypatch.setattr("quodeq.services.evidence_rescore.score_evidence", _boom)
    out = score_dimension_from_evidence(
        run_dir, DIM, dismissed=set(), deleted=set(),
        source_file_count=10, files_read=5, params=DEFAULT_PARAMS)
    assert out is None


def test_dismiss_by_principle_key_matches_no_req_finding(run_dir):
    """The UI stores a dismiss key as `req || principle`. For a finding whose
    evidence row carries no req, the stored key is (principle, file, line);
    the rescore must fall back to the principle group like the live counter
    matcher does, or the counter hides the finding while the grade never moves.
    """
    lines = [
        _line("M-MOD-1", "a.kt", 10),
        {k: v for k, v in _line(None, "b.kt", 7, sev="critical").items() if k != "req"},
        _line("C-1", "a.kt", 1, t="compliance"),
    ]
    _write_evidence(run_dir, lines)
    base = score_dimension_from_evidence(
        run_dir, DIM, dismissed=set(), deleted=set(),
        source_file_count=10, files_read=5, params=DEFAULT_PARAMS)
    out = score_dimension_from_evidence(
        run_dir, DIM, dismissed={("Modularity", "b.kt", 7)}, deleted=set(),
        source_file_count=10, files_read=5, params=DEFAULT_PARAMS)
    assert out.principles["Modularity"].deductions.critical_type_count \
        == base.principles["Modularity"].deductions.critical_type_count - 1
