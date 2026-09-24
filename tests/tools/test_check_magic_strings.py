"""Unit tests and gate for tools/check_magic_strings.py: compared and repeated string literals."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import check_magic_strings

TOOLS = Path(__file__).resolve().parents[2] / "tools"


def _keys(tmp_path: Path, body: str) -> set[str]:
    p = tmp_path / "quodeq" / "mod.py"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return {h.key for h in check_magic_strings.scan_tree(tmp_path)}


def test_gate_passes_on_current_tree():
    proc = subprocess.run([sys.executable, str(TOOLS / "check_magic_strings.py")], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_flags_equality_membership_and_case(tmp_path):
    keys = _keys(tmp_path, (
        "def f(s):\n"
        "    if s == 'alpha':\n"
        "        pass\n"
        "    if s in ('beta', 'gamma'):\n"
        "        pass\n"
        "    if s not in frozenset({'delta'}):\n"
        "        pass\n"
        "    match s:\n"
        "        case 'epsilon':\n"
        "            pass\n"
    ))
    assert keys == {f"quodeq/mod.py:C:{w}" for w in ("alpha", "beta", "gamma", "delta", "epsilon")}


def test_flags_a_literal_repeated_three_times(tmp_path):
    keys = _keys(tmp_path, "def f(a, b, c):\n    return [a / 'status.json', b / 'status.json', c / 'status.json']\n")
    assert keys == {"quodeq/mod.py:R:status.json"}


def test_two_copies_are_not_a_repeat(tmp_path):
    assert _keys(tmp_path, "def f(a, b):\n    return [a / 'status.json', b / 'status.json']\n") == set()


def test_key_positions_are_not_flagged(tmp_path):
    body = (
        "def f(d, obj):\n"
        "    x = {'name': 1, 'name2': d['name'], 'name3': d.get('name')}\n"
        "    return 'name' in d, getattr(obj, 'name'), d.pop('name'), open(p, encoding='utf-8'), open(p, encoding='utf-8'), open(p, encoding='utf-8')\n"
    )
    assert _keys(tmp_path, body) == set()


def test_messages_docstrings_fstrings_and_constants_are_not_flagged(tmp_path):
    body = (
        '"""Module doc mentions ready, ready, ready."""\n'
        "import logging\n"
        "log = logging.getLogger(__name__)\n"
        "READY = 'ready'\n"
        "class K:\n"
        "    MODE = 'ready'\n"
        "def f(x: 'Thing') -> 'Thing':\n"
        "    log.warning('ready'); log.info('ready'); print('ready')\n"
        "    if x is None:\n"
        "        raise ValueError('ready')\n"
        "    return f'ready {x}'\n"
        "if __name__ == '__main__':\n"
        "    f(None)\n"
    )
    assert _keys(tmp_path, body) == set()


def test_separators_and_vocab_words_are_not_flagged(tmp_path):
    body = "def f(s):\n    return s == ', ', s == '..', s == 'running', s in ('done', 'failed')\n"
    assert _keys(tmp_path, body) == set()


def test_module_constant_comparison_is_the_fix(tmp_path):
    body = "ALPHA = 'alpha'\ndef f(s):\n    return s == ALPHA\n"
    assert _keys(tmp_path, body) == set()


def test_keys_carry_no_line_numbers(tmp_path):
    first = _keys(tmp_path, "def f(s):\n    return s == 'alpha'\n")
    moved = _keys(tmp_path, "\n\n\ndef f(s):\n    return s == 'alpha'\n")
    assert first == moved == {"quodeq/mod.py:C:alpha"}


def test_baseline_is_empty():
    lines = [l for l in (TOOLS / "magic_strings_baseline.txt").read_text().splitlines() if l.strip() and not l.startswith("#")]
    assert lines == []
