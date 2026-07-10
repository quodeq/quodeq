import json
import stat
import sys
from pathlib import Path

import pytest

from quodeq_bench.runner import RunConfig, RunError, replay_case, run_case

_FAKE_QUODEQ = """#!/usr/bin/env python3
import json, sys
from pathlib import Path

args = sys.argv[1:]
out = Path(args[args.index("-o") + 1])
evidence = out / "proj" / "run" / "evidence"
evidence.mkdir(parents=True)
line = {
    "schema_version": 1, "p": "Confidentiality", "t": "violation",
    "d": "security", "w": "hardcoded secret", "file": "config.py", "line": 1,
    "snippet": "API_KEY = ...", "severity": "critical", "reason": "secret",
    "req": "S-CON-1", "vt": "hardcoded-secret", "refs": ["CWE-798"],
}
(evidence / "security_evidence.jsonl").write_text(json.dumps(line) + "\\n")
"""

_FAKE_QUODEQ_WITH_ERROR = _FAKE_QUODEQ.replace(
    '(evidence / "security_evidence.jsonl").write_text(json.dumps(line) + "\\n")',
    '(evidence / "security_evidence.jsonl").write_text('
    'json.dumps(line) + "\\n" + json.dumps('
    '{"_marker": "file_done", "file": "config.py", "status": "error"}) + "\\n")',
)


def _make_fake_quodeq(tmp_path: Path, body: str) -> tuple[str, ...]:
    script = tmp_path / "fake_quodeq.py"
    script.write_text(body, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return (sys.executable, str(script))


def _make_case(tmp_path: Path) -> Path:
    case = tmp_path / "py-sec-basic"
    case.mkdir()
    (case / "config.py").write_text('API_KEY = "sk-live-x"\n', encoding="utf-8")
    (case / "truth.json").write_text("{}", encoding="utf-8")
    return case


def test_run_case_collects_findings(tmp_path: Path) -> None:
    cfg = RunConfig(
        provider="claude", model="test-model",
        quodeq_cmd=_make_fake_quodeq(tmp_path, _FAKE_QUODEQ),
    )
    findings = run_case(_make_case(tmp_path), cfg, tmp_path / "work")
    assert len(findings) == 1
    assert findings[0].refs == ("CWE-798",)
    assert not (tmp_path / "work" / "repo" / "truth.json").exists()


def test_run_case_raises_on_nonzero_exit(tmp_path: Path) -> None:
    cfg = RunConfig(
        provider="claude", model="test-model",
        quodeq_cmd=_make_fake_quodeq(tmp_path, "import sys; sys.exit(3)\n"),
    )
    with pytest.raises(RunError, match="exit"):
        run_case(_make_case(tmp_path), cfg, tmp_path / "work")


def test_run_case_raises_when_no_evidence(tmp_path: Path) -> None:
    cfg = RunConfig(
        provider="claude", model="test-model",
        quodeq_cmd=_make_fake_quodeq(tmp_path, "pass\n"),
    )
    with pytest.raises(RunError, match="evidence"):
        run_case(_make_case(tmp_path), cfg, tmp_path / "work")


def test_run_case_warns_on_errored_files(tmp_path: Path, capsys) -> None:
    cfg = RunConfig(
        provider="claude", model="test-model",
        quodeq_cmd=_make_fake_quodeq(tmp_path, _FAKE_QUODEQ_WITH_ERROR),
    )
    findings = run_case(_make_case(tmp_path), cfg, tmp_path / "work")
    assert len(findings) == 1
    assert "failed to analyze 1 file(s)" in capsys.readouterr().err


def test_replay_case(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    line = {
        "t": "violation", "d": "security", "w": "x", "file": "a.py",
        "line": 3, "severity": "major", "req": "S-CON-1", "vt": "x",
        "refs": ["CWE-89"],
    }
    (evidence / "security_evidence.jsonl").write_text(
        json.dumps(line) + "\n", encoding="utf-8"
    )
    assert len(replay_case(evidence)) == 1
