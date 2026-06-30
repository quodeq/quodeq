# tests/ci/test_export_cli.py
import argparse
import json
from pathlib import Path

from quodeq.ci.export_cli import handle_export


def _write_report(eval_dir: Path, dimension: str, violations: list[dict]) -> None:
    eval_dir.mkdir(parents=True, exist_ok=True)
    (eval_dir / f"{dimension}.json").write_text(
        json.dumps({"dimension": dimension, "violations": violations, "compliance": []}),
        encoding="utf-8",
    )


def _args(**kw) -> argparse.Namespace:
    base = {
        "export_format": "sarif",
        "evaluation_dir": None,
        "output": None,
        "min_severity": None,
        "with_snippets": False,
    }
    base.update(kw)
    return argparse.Namespace(**base)


def test_handle_export_writes_valid_sarif(tmp_path):
    eval_dir = tmp_path / "evaluation"
    _write_report(eval_dir, "reliability", [
        {"principle": "Fault Tolerance", "file": "app.py", "line": 1, "severity": "major",
         "title": "t", "reason": "r", "req": "R-FT-1", "req_refs": []},
    ])
    out = tmp_path / "out.sarif"

    code = handle_export(_args(evaluation_dir=str(eval_dir), output=str(out)))

    assert code == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["version"] == "2.1.0"
    assert len(doc["runs"][0]["results"]) == 1


def test_handle_export_missing_dir_returns_error(tmp_path, capsys):
    out = tmp_path / "out.sarif"
    code = handle_export(_args(evaluation_dir=str(tmp_path / "nope"), output=str(out)))
    assert code == 1
    assert not out.exists()


def test_handle_export_unknown_format_returns_error(tmp_path):
    code = handle_export(_args(export_format="xml", evaluation_dir=str(tmp_path), output="x"))
    assert code == 1
