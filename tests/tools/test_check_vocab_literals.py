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


def test_baseline_is_empty():
    lines = [l for l in (TOOLS / "vocab_literals_baseline.txt").read_text().splitlines() if l.strip() and not l.startswith("#")]
    assert lines == []


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


def test_flags_writes_to_vocabulary_targets(tmp_path):
    _write(tmp_path, "src/quodeq/services/x.py", (
        'class C:\n'
        '    def f(self, other):\n'
        '        self.status = "done"\n'
        '        state = "running"\n'
        '        severity: str = "critical"\n'
        '        grade, other.exit_reason = "Poor", "cancelled"\n'
    ))
    hits = check_vocab_literals.scan_tree(tmp_path / "src")
    assert [(h.line, h.literal) for h in hits] == [
        (3, "done"), (4, "running"), (5, "critical"), (6, "Poor"), (6, "cancelled"),
    ]


def test_writes_to_non_vocabulary_targets_are_not_flagged(tmp_path):
    _write(
        tmp_path, "src/quodeq/services/x.py",
        'def f(obj):\n    name = "done"\n    obj.label = "running"\n    return name\n',
    )
    assert check_vocab_literals.scan_tree(tmp_path / "src") == []


def test_flags_collections_of_two_or_more_words_from_one_vocabulary(tmp_path):
    _write(tmp_path, "src/quodeq/services/x.py", (
        '_TERMINAL = frozenset({"done", "failed"})\n'
        'CHOICES = ["critical", "major", "minor"]\n'
        'PAIR = ("openrouter", "custom")\n'
        'MIXED = {"Poor", "unknown"}\n'
        'ACROSS = ("critical", "Poor", "claude")\n'
    ))
    hits = check_vocab_literals.scan_tree(tmp_path / "src")
    assert [(h.line, h.literal) for h in hits] == [
        (1, "done"), (1, "failed"),
        (2, "critical"), (2, "major"), (2, "minor"),
        (3, "custom"), (3, "openrouter"),
    ]


def test_a_membership_collection_is_reported_once_per_literal(tmp_path):
    _write(tmp_path, "src/quodeq/services/x.py", 'def f(s):\n    return s in ("done", "failed")\n')
    hits = check_vocab_literals.scan_tree(tmp_path / "src")
    assert [(h.line, h.literal) for h in hits] == [(2, "done"), (2, "failed")]


def test_flags_vocabulary_default_of_a_vocabulary_key_get(tmp_path):
    _write(tmp_path, "src/quodeq/services/x.py", (
        'def f(d):\n'
        '    a = d.get("state", "running")\n'
        '    b = d.get("severity", "minor")\n'
        '    c = d.get("label", "done")\n'
        '    e = d.get("status")\n'
        '    return a, b, c, e\n'
    ))
    hits = check_vocab_literals.scan_tree(tmp_path / "src")
    assert [(h.line, h.literal) for h in hits] == [(2, "running"), (3, "minor")]


def test_left_operand_of_membership_is_a_key_test(tmp_path):
    _write(tmp_path, "src/quodeq/services/x.py", (
        'def f(payload, s):\n'
        '    if "error" in payload:\n'
        '        return payload["error"]\n'
        '    if "done" not in payload:\n'
        '        return None\n'
        '    return s in ("ok",) or "failed" == s\n'
    ))
    hits = check_vocab_literals.scan_tree(tmp_path / "src")
    assert [(h.line, h.literal) for h in hits] == [(6, "failed"), (6, "ok")]
