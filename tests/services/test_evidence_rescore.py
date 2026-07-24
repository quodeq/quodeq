"""Evidence-based rescore reproduces scan-time scoring exactly."""
import json
from pathlib import Path

import pytest

from quodeq.core.evidence.parser import EvidenceContext, parse_jsonl_to_evidence
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
