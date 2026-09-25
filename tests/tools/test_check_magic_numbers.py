"""Unit tests and gate for tools/check_magic_numbers.py: passed, returned and compared numeric literals."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import check_magic_numbers

TOOLS = Path(__file__).resolve().parents[2] / "tools"


def _keys(tmp_path: Path, body: str, rel: str = "quodeq/mod.py") -> set[str]:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return {h.key for h in check_magic_numbers.scan_tree(tmp_path)}


def test_gate_passes_on_current_tree():
    proc = subprocess.run([sys.executable, str(TOOLS / "check_magic_numbers.py")], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_flags_positional_keyword_and_default_arguments(tmp_path):
    body = (
        "def f(x, retries=3, *, delay=0.25):\n"
        "    g(x, 30)\n"
        "    g(x, timeout=45)\n"
        "    h = lambda y=7: y\n"
    )
    assert _keys(tmp_path, body) == {f"quodeq/mod.py:A:{v}" for v in ("3", "0.25", "30", "45", "7")}


def test_flags_literals_inside_an_argument_display(tmp_path):
    keys = _keys(tmp_path, "def f():\n    g([5, 10], {'a': 20}, (30,))\n")
    assert keys == {f"quodeq/mod.py:A:{v}" for v in ("5", "10", "20", "30")}


def test_flags_plain_and_tuple_returns(tmp_path):
    keys = _keys(tmp_path, "def f(x):\n    if x:\n        return 5\n    return x, 7\n")
    assert keys == {"quodeq/mod.py:R:5", "quodeq/mod.py:R:7"}


def test_flags_compare_operands_on_either_side(tmp_path):
    keys = _keys(tmp_path, "def f(n):\n    return n > 50 or 3 <= n < 9 or n in (11, 12)\n")
    assert keys == {f"quodeq/mod.py:C:{v}" for v in ("50", "3", "9", "11", "12")}


def test_small_values_and_bools_are_not_flagged(tmp_path):
    body = (
        "def f(x=0, y=1, z=-1, w=2, v=-2, u=1.0, t=True):\n"
        "    g(x, 0.0, -2.0, flag=False)\n"
        "    return x > 1 or x == -1 or x != 2\n"
    )
    assert _keys(tmp_path, body) == set()


def test_negative_literals_key_as_one_value(tmp_path):
    keys = _keys(tmp_path, "def f(x=-5):\n    return x > -0.5\n")
    assert keys == {"quodeq/mod.py:A:-5", "quodeq/mod.py:C:-0.5"}


def test_key_literal_is_the_repr(tmp_path):
    keys = _keys(tmp_path, "def f():\n    g(1e-6, 0.25, 1_000, 0x10)\n")
    assert keys == {f"quodeq/mod.py:A:{v}" for v in ("1e-06", "0.25", "1000", "16")}


def test_module_and_class_constants_are_not_flagged(tmp_path):
    body = (
        "TIMEOUT_S = 30\n"
        "LIMITS: tuple[int, ...] = (5, 10)\n"
        "TABLE = {'a': [3, 4], 'b': {7}}\n"
        "CLIENT = make(timeout=45)\n"
        "class K:\n"
        "    SIZE = 64\n"
        "    width: int = field(default=80)\n"
    )
    assert _keys(tmp_path, body) == set()


def test_function_local_assignment_calls_are_flagged(tmp_path):
    assert _keys(tmp_path, "def f():\n    client = make(timeout=45)\n") == {"quodeq/mod.py:A:45"}


def test_arithmetic_operands_and_anything_under_them_are_not_flagged(tmp_path):
    body = "def f(x, n):\n    g(x * 1000, n // 3, h(n + 5))\n    return x / 60\n"
    assert _keys(tmp_path, body) == set()


def test_subscripts_and_slices_are_not_flagged(tmp_path):
    body = "def f(xs):\n    g(xs[3], xs[4:8], xs[::5])\n    return xs[7] > xs[-3]\n"
    assert _keys(tmp_path, body) == set()


def test_exempt_builtins_are_not_flagged(tmp_path):
    body = (
        "import sys\n"
        "def f(xs, x):\n"
        "    for i in range(3, 10, 5): pass\n"
        "    for i, v in enumerate(xs, 5): pass\n"
        "    g(round(x, 3), min(x, 9), max(x, 7), abs(-4), pow(x, 3), divmod(x, 7))\n"
        "    g(zip(xs, [5, 6]), sorted(xs, reverse=3), int('7', 16), float(5), str(9))\n"
        "    sys.exit(3)\n"
        "    exit(4)\n"
    )
    assert _keys(tmp_path, body) == set()


def test_sleep_and_dict_get_defaults_are_flagged(tmp_path):
    keys = _keys(tmp_path, "import time\ndef f(d):\n    time.sleep(5)\n    d.get('k', 30)\n")
    assert keys == {"quodeq/mod.py:A:5", "quodeq/mod.py:A:30"}


def test_octal_modes_are_not_flagged(tmp_path):
    body = "import os\ndef f(p):\n    os.chmod(p, 0o600)\n    p.mkdir(mode=0O755)\n    return 0o644\n"
    assert _keys(tmp_path, body) == set()


def test_http_status_members_are_not_flagged(tmp_path):
    body = "import http\nfrom http import HTTPStatus\ndef f(r):\n    g(HTTPStatus(404), http.HTTPStatus(500))\n    return r.status == HTTPStatus.NOT_FOUND\n"
    assert _keys(tmp_path, body) == set()


def test_annotations_are_not_flagged(tmp_path):
    body = "from typing import Literal\ndef f(x: Literal[5, 6]) -> Literal[7]:\n    y: Literal[8] = x\n    return y\n"
    assert _keys(tmp_path, body) == set()


def test_fstrings_and_format_specs_are_not_flagged(tmp_path):
    body = "def f(x):\n    return g(f'{x:.3f} {x:>{10}} {h(7)}')\n"
    assert _keys(tmp_path, body) == set()


def test_keys_carry_no_line_numbers(tmp_path):
    first = _keys(tmp_path, "def f(n):\n    return n > 50\n")
    moved = _keys(tmp_path, "\n\n\ndef f(n):\n    return n > 50\n")
    assert first == moved == {"quodeq/mod.py:C:50"}


def test_one_hit_per_key(tmp_path):
    _keys(tmp_path, "def f():\n    g(5)\n    g(5)\n")
    hits = check_magic_numbers.scan_tree(tmp_path)
    assert [h.key for h in hits] == ["quodeq/mod.py:A:5"]
    assert hits[0].line == 2


def test_ui_tree_is_not_scanned(tmp_path):
    assert _keys(tmp_path, "def f():\n    g(5)\n", rel="quodeq/ui/tool.py") == set()


def test_describe_shows_line_rule_literal_and_source(tmp_path):
    _keys(tmp_path, "def f(n):\n    return n > 50\n")
    [hit] = check_magic_numbers.scan_tree(tmp_path)
    assert check_magic_numbers.describe(hit) == "quodeq/mod.py:2 [C] 50: return n > 50"


def test_baseline_is_empty():
    lines = [l for l in (TOOLS / "magic_numbers_baseline.txt").read_text().splitlines() if l.strip() and not l.startswith("#")]
    assert lines == []
