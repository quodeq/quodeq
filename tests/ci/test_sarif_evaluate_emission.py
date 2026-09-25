import json
from pathlib import Path

from quodeq.cli_evaluation import write_sarif_if_requested


def _seed_reports(eval_dir: Path) -> None:
    eval_dir.mkdir(parents=True, exist_ok=True)
    (eval_dir / "reliability.json").write_text(
        json.dumps({
            "dimension": "reliability",
            "violations": [{"principle": "Fault Tolerance", "file": "app.py", "line": 1,
                            "severity": "major", "title": "t", "reason": "r", "req": "R-FT-1", "req_refs": []}],
            "compliance": [],
        }),
        encoding="utf-8",
    )


class _Args:
    def __init__(self, **kw):
        self.sarif = kw.get("sarif")
        self.min_severity = kw.get("min_severity")
        self.with_snippets = kw.get("with_snippets", False)


def test_write_sarif_emits_file_on_success(tmp_path):
    eval_dir = tmp_path / "evaluation"
    _seed_reports(eval_dir)
    out = tmp_path / "q.sarif"

    write_sarif_if_requested(_Args(sarif=str(out)), eval_dir)

    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["version"] == "2.1.0"
    assert len(doc["runs"][0]["results"]) == 1


def test_write_sarif_is_fail_soft(tmp_path):
    eval_dir = tmp_path / "evaluation"
    _seed_reports(eval_dir)
    # Output path under a *file* (not a dir) -> write raises; must be swallowed.
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    bad_out = blocker / "nested" / "q.sarif"

    # Must NOT raise.
    write_sarif_if_requested(_Args(sarif=str(bad_out)), eval_dir)
    assert not bad_out.exists()


def test_write_sarif_noop_when_flag_absent(tmp_path):
    eval_dir = tmp_path / "evaluation"
    _seed_reports(eval_dir)
    # sarif=None -> nothing written, no error.
    write_sarif_if_requested(_Args(sarif=None), eval_dir)


def test_write_sarif_is_fail_soft_on_malformed_report(tmp_path):
    """A corrupt report JSON raises json.JSONDecodeError (a ValueError
    subclass) out of load_evaluation_reports; must be swallowed too."""
    eval_dir = tmp_path / "evaluation"
    eval_dir.mkdir(parents=True, exist_ok=True)
    (eval_dir / "reliability.json").write_text("{not valid json", encoding="utf-8")
    out = tmp_path / "q.sarif"

    write_sarif_if_requested(_Args(sarif=str(out)), eval_dir)  # must NOT raise
    assert not out.exists()
