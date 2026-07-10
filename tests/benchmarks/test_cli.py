import json
from pathlib import Path

from quodeq_bench.cli import main

_EVIDENCE_LINE = {
    "t": "violation", "d": "security", "w": "hardcoded secret",
    "file": "config.py", "line": 1, "severity": "critical",
    "req": "S-CON-1", "vt": "hardcoded-secret", "refs": ["CWE-798"],
}
_TRUTH = {
    "language": "python",
    "exhaustive": True,
    "clean_files": [],
    "labels": [
        {
            "file": "config.py", "line": 1, "anchor": "API_KEY",
            "dimension": "security", "cwes": [798], "reqs": ["S-CON-1"],
            "severity": "critical", "note": "hardcoded key",
        }
    ],
}


def _corpus_with_replay(tmp_path: Path) -> tuple[Path, Path]:
    case = tmp_path / "corpus" / "py-sec-basic"
    case.mkdir(parents=True)
    (case / "config.py").write_text('API_KEY = "sk-live-x"\n', encoding="utf-8")
    (case / "truth.json").write_text(json.dumps(_TRUTH), encoding="utf-8")
    replay = tmp_path / "replay" / "py-sec-basic"
    replay.mkdir(parents=True)
    (replay / "security_evidence.jsonl").write_text(
        json.dumps(_EVIDENCE_LINE) + "\n", encoding="utf-8"
    )
    return tmp_path / "corpus", tmp_path / "replay"


def test_run_replay_writes_report(tmp_path: Path) -> None:
    corpus, replay = _corpus_with_replay(tmp_path)
    out = tmp_path / "results"
    code = main([
        "run", "--corpus", str(corpus), "--provider", "claude",
        "--model", "test", "--replay-root", str(replay), "--out", str(out),
    ])
    assert code == 0
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["metrics"]["security"]["recall"] == 1.0
    assert report["metrics"]["security"]["precision"] == 1.0


def test_compare_exit_codes(tmp_path: Path) -> None:
    good = {"meta": {}, "errored": False,
            "metrics": {"security": {"precision": 0.9, "recall": 0.9}}}
    bad = {"meta": {}, "errored": False,
           "metrics": {"security": {"precision": 0.5, "recall": 0.9}}}
    base = tmp_path / "base.json"
    cand_ok = tmp_path / "ok.json"
    cand_bad = tmp_path / "bad.json"
    base.write_text(json.dumps(good), encoding="utf-8")
    cand_ok.write_text(json.dumps(good), encoding="utf-8")
    cand_bad.write_text(json.dumps(bad), encoding="utf-8")
    assert main(["compare", str(base), str(cand_ok)]) == 0
    assert main(["compare", str(base), str(cand_bad)]) == 1


def test_compare_errored_candidate_exits_2(tmp_path: Path) -> None:
    base = tmp_path / "base.json"
    cand = tmp_path / "cand.json"
    base.write_text(json.dumps({"bootstrap": True, "metrics": {}}), encoding="utf-8")
    cand.write_text(
        json.dumps({"meta": {}, "errored": True, "metrics": {}}), encoding="utf-8"
    )
    assert main(["compare", str(base), str(cand)]) == 2


def test_markdown_prints_table(tmp_path: Path, capsys) -> None:
    report = {"meta": {"provider": "p", "model": "m"}, "errored": False,
              "metrics": {"security": {
                  "precision": 0.9, "recall": 0.8, "f1": 0.85,
                  "fp_density": 0.1, "total_labels": 4}}}
    path = tmp_path / "r.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    assert main(["markdown", str(path)]) == 0
    assert "| security |" in capsys.readouterr().out


def test_run_replay_missing_case_dir_exits_2(tmp_path: Path) -> None:
    corpus, _replay = _corpus_with_replay(tmp_path)
    out = tmp_path / "results"
    code = main([
        "run", "--corpus", str(corpus), "--provider", "claude",
        "--model", "test", "--replay-root", str(tmp_path / "empty-replay"),
        "--out", str(out),
    ])
    assert code == 2
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["errored"] is True
