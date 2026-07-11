import json
import shutil
from pathlib import Path

from quodeq_bench.cli import main

_ROOT = Path(__file__).resolve().parents[2]
_CASE = _ROOT / "benchmarks" / ".corpus" / "synthetic" / "py-security"
_FIXTURE = Path(__file__).parent / "fixtures" / "replay" / "py-security"


def test_replay_pipeline_end_to_end(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    (corpus / "py-security").parent.mkdir(parents=True)
    shutil.copytree(_CASE, corpus / "py-security")
    replay = tmp_path / "replay"
    shutil.copytree(_FIXTURE, replay / "py-security")
    out = tmp_path / "results"

    code = main([
        "run", "--corpus", str(corpus), "--provider", "claude",
        "--model", "replay", "--replay-root", str(replay), "--out", str(out),
    ])
    assert code == 0
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    sec = report["metrics"]["security"]
    assert sec["total_labels"] == 4
    assert sec["matched_labels"] == 3
    assert sec["recall"] == 0.75
    assert sec["fp"] == 1
    assert sec["precision"] == 0.75
