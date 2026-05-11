import json
from pathlib import Path

from quodeq.verifier.service import (
    LocatedFinding,
    jsonl_finding_locator,
)


def _write_eval(root: Path, eval_id: str, run_id: str, dimension: str, findings: list[dict]) -> None:
    eval_dir = root / eval_id / run_id / "evaluation"
    eval_dir.mkdir(parents=True, exist_ok=True)
    (eval_dir / f"{dimension}.json").write_text(json.dumps({"findings": findings}))


def test_locator_finds_finding_by_id(tmp_path: Path):
    _write_eval(
        tmp_path,
        "eval-1",
        "run-1",
        "flexibility",
        [
            {
                "id": "f1",
                "file": "api/app.py",
                "line": 6,
                "title": "Hardcoded filesystem dependency",
                "principle": "Adaptability",
                "severity": "major",
            }
        ],
    )
    locator = jsonl_finding_locator(tmp_path)
    out = locator("eval-1", "flexibility", "f1")
    assert out is not None
    assert out.file == "api/app.py"
    assert out.line == 6
    assert "Adaptability" in out.category
    assert out.severity == "major"


def test_locator_returns_none_for_missing(tmp_path: Path):
    locator = jsonl_finding_locator(tmp_path)
    out = locator("nonexistent", "flexibility", "f1")
    assert out is None


def test_locator_searches_multiple_runs(tmp_path: Path):
    _write_eval(tmp_path, "eval-1", "run-1", "flexibility", [
        {"id": "f1", "file": "a.py", "line": 1, "title": "x", "principle": "Adaptability", "severity": "minor"},
    ])
    _write_eval(tmp_path, "eval-1", "run-2", "flexibility", [
        {"id": "f2", "file": "b.py", "line": 2, "title": "y", "principle": "Adaptability", "severity": "minor"},
    ])
    locator = jsonl_finding_locator(tmp_path)
    out2 = locator("eval-1", "flexibility", "f2")
    assert out2 is not None
    assert out2.file == "b.py"


def test_locator_finds_finding_by_composite_id(tmp_path: Path):
    # No explicit id field -- real findings shape
    _write_eval(
        tmp_path,
        "eval-1",
        "run-1",
        "flexibility",
        [
            {
                "file": "src/api/app.py",
                "line": 34,
                "title": "Hardcoded filesystem dependency",
                "principle": "Adaptability",
                "severity": "major",
            }
        ],
    )
    locator = jsonl_finding_locator(tmp_path)

    # Compute the same composite id the UI would compute
    from quodeq.verifier.service import _compute_finding_id
    fid = _compute_finding_id({
        "file": "src/api/app.py",
        "line": 34,
        "title": "Hardcoded filesystem dependency",
    })

    out = locator("eval-1", "flexibility", fid)
    assert out is not None
    assert out.file == "src/api/app.py"
    assert out.line == 34
    assert "Adaptability" in out.category


def test_fnv1a32_matches_known_value():
    """Pin the hash function to a known output so JS and Python implementations
    can be cross-checked."""
    from quodeq.verifier.service import _fnv1a32
    # Empty string FNV-1a 32-bit is the offset basis itself
    assert _fnv1a32("") == "811c9dc5"
    # Known FNV-1a test vector: "foobar" -> 0xbf9cf968
    assert _fnv1a32("foobar") == "bf9cf968"
