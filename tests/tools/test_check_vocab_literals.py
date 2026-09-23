"""Unit tests and gate for tools/check_vocab_literals.py: bare vocabulary literals."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import check_vocab_literals

TOOLS = Path(__file__).resolve().parents[2] / "tools"


def _write(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def test_gate_passes_on_current_tree():
    proc = subprocess.run(
        [sys.executable, str(TOOLS / "check_vocab_literals.py")], capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_flags_comparison_membership_match_and_keyword(tmp_path):
    _write(tmp_path, "src/quodeq/services/x.py", (
        'def f(s, job):\n'
        '    if s == "running":\n'
        '        pass\n'
        '    if s in {"done", "failed"}:\n'
        '        pass\n'
        '    match s:\n'
        '        case "cancelled":\n'
        '            pass\n'
        '    job.set(status="done")\n'
        '    return {"status": "done"}\n'
    ))
    hits = check_vocab_literals.scan_tree(tmp_path / "src")
    assert [(h.line, h.literal) for h in hits] == [
        (2, "running"), (4, "done"), (4, "failed"), (7, "cancelled"), (9, "done"), (10, "done"),
    ]


def test_ignores_dict_keys_docstrings_fstrings_and_other_keywords(tmp_path):
    _write(tmp_path, "src/quodeq/services/x.py", (
        'def f(d, log):\n'
        '    """Returns "done" when done."""\n'
        '    d["error"] = "boom"\n'
        '    log(f"state is {d}")\n'
        '    log("running")\n'
        '    return d.get("status")\n'
    ))
    assert check_vocab_literals.scan_tree(tmp_path / "src") == []


def test_home_modules_are_exempt(tmp_path):
    _write(
        tmp_path, "src/quodeq/core/run/state.py",
        'X = {"complete": 1}\ndef f(s):\n    return s == "done"\n',
    )
    assert check_vocab_literals.scan_tree(tmp_path / "src") == []


def test_non_vocabulary_words_are_not_flagged(tmp_path):
    _write(
        tmp_path, "src/quodeq/services/x.py",
        'def f(s):\n    return s == "utf-8" or s in ("name", "type")\n',
    )
    assert check_vocab_literals.scan_tree(tmp_path / "src") == []
