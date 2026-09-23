"""Unit tests and gate for tools/check_private_imports.py: rule A/B private imports."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import _private_imports_rules as rules
import check_private_imports

TOOLS = Path(__file__).resolve().parents[2] / "tools"


def _write(tmp_path: Path, relpath: str, source: str) -> Path:
    f = tmp_path / relpath
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(source, encoding="utf-8")
    return f


def _scan_src(tmp_path: Path) -> list[rules.Hit]:
    src_root = tmp_path / "src" / "quodeq"
    return rules.scan_tree(src_root, src_root, tmp_path)


def _scan_tests(tmp_path: Path) -> list[rules.Hit]:
    return rules.scan_tree(tmp_path / "tests", tmp_path / "src" / "quodeq", tmp_path)


def test_gate_passes_on_current_tree():
    proc = subprocess.run(
        [sys.executable, str(TOOLS / "check_private_imports.py")],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_rule_a_flags_cross_package_private_name(tmp_path):
    _write(tmp_path, "src/quodeq/services/y.py", "def _helper():\n    return 1\n")
    _write(tmp_path, "src/quodeq/api/x.py", "from quodeq.services.y import _helper\n")
    hits = _scan_src(tmp_path)
    assert [(h.kind, h.module, h.name) for h in hits] == [
        ("private-name", "quodeq.services.y", "_helper"),
    ]


def test_rule_a_allows_same_package_private_name_under_rules_a_b(tmp_path):
    _write(tmp_path, "src/quodeq/services/y.py", "def _helper():\n    return 1\n")
    _write(tmp_path, "src/quodeq/services/z.py", "from quodeq.services.y import _helper\n")
    assert _scan_src(tmp_path) == []


def test_rule_b_flags_private_module_from_import(tmp_path):
    _write(tmp_path, "src/quodeq/services/_impl.py", "def f():\n    return 1\n")
    _write(tmp_path, "src/quodeq/api/x.py", "from quodeq.services._impl import f\n")
    hits = _scan_src(tmp_path)
    assert [(h.kind, h.module, h.name) for h in hits] == [
        ("private-module", "quodeq.services._impl", "f"),
    ]


def test_rule_b_allows_same_package_private_module(tmp_path):
    _write(tmp_path, "src/quodeq/services/_impl.py", "def f():\n    return 1\n")
    _write(tmp_path, "src/quodeq/services/z.py", "from quodeq.services._impl import f\n")
    assert _scan_src(tmp_path) == []


def test_relative_imports_never_flagged_under_rules_a_b(tmp_path):
    _write(tmp_path, "src/quodeq/services/_impl.py", "def f():\n    return 1\n\ndef _g():\n    return 2\n")
    _write(tmp_path, "src/quodeq/api/x.py", "from ._impl import f\nfrom . import _thing\n")
    assert _scan_src(tmp_path) == []


def test_from_package_import_of_existing_submodule_is_rule_b(tmp_path):
    """`from quodeq.services import _impl` where _impl.py exists: rule B."""
    _write(tmp_path, "src/quodeq/services/_impl.py", "X = 1\n")
    _write(tmp_path, "src/quodeq/api/x.py", "from quodeq.services import _impl\n")
    hits = _scan_src(tmp_path)
    assert [(h.kind, h.module, h.name) for h in hits] == [
        ("private-module", "quodeq.services", "_impl"),
    ]


def test_from_package_import_of_private_name_is_rule_a(tmp_path):
    """`from quodeq.services import _priv` where _priv is not a file: rule A."""
    _write(tmp_path, "src/quodeq/services/y.py", "X = 1\n")
    _write(tmp_path, "src/quodeq/api/x.py", "from quodeq.services import _priv\n")
    hits = _scan_src(tmp_path)
    assert [(h.kind, h.module, h.name) for h in hits] == [
        ("private-name", "quodeq.services", "_priv"),
    ]


def test_plain_import_of_private_module_is_rule_b(tmp_path):
    _write(tmp_path, "src/quodeq/services/_impl.py", "X = 1\n")
    _write(tmp_path, "src/quodeq/api/x.py", "import quodeq.services._impl as m\n")
    hits = _scan_src(tmp_path)
    assert [(h.kind, h.module, h.name) for h in hits] == [
        ("private-module", "quodeq.services._impl", "m"),
    ]


def test_plain_import_of_private_module_allowed_from_same_package(tmp_path):
    _write(tmp_path, "src/quodeq/services/_impl.py", "X = 1\n")
    _write(tmp_path, "src/quodeq/services/z.py", "import quodeq.services._impl as m\n")
    assert _scan_src(tmp_path) == []


def test_dunder_name_is_not_private(tmp_path):
    _write(tmp_path, "src/quodeq/services/y.py", "__version__ = '1'\n")
    _write(tmp_path, "src/quodeq/api/x.py", "from quodeq.services.y import __version__\n")
    assert _scan_src(tmp_path) == []


def test_private_package_in_middle_of_dotted_path_is_rule_b(tmp_path):
    _write(tmp_path, "src/quodeq/pkg/_sub/mod.py", "X = 1\n")
    _write(tmp_path, "src/quodeq/api/x.py", "from quodeq.pkg._sub.mod import X\n")
    hits = _scan_src(tmp_path)
    assert [(h.kind, h.module, h.name) for h in hits] == [
        ("private-module", "quodeq.pkg._sub.mod", "X"),
    ]
    # Allowed from directly inside `pkg/`, the package that contains `_sub`.
    _write(tmp_path, "src/quodeq/pkg/user.py", "from quodeq.pkg._sub.mod import X\n")
    assert [(h.path.name, h.kind) for h in _scan_src(tmp_path)] == [("x.py", "private-module")]


def test_tests_tree_flags_private_imports_of_src(tmp_path):
    """A test file can never be the "same package" as the src it exercises."""
    _write(tmp_path, "src/quodeq/services/_impl.py", "def f():\n    return 1\n")
    _write(tmp_path, "tests/services/test_impl.py", "from quodeq.services._impl import f\n")
    hits = _scan_tests(tmp_path)
    assert [(h.kind, h.module, h.name) for h in hits] == [
        ("private-module", "quodeq.services._impl", "f"),
    ]


def test_syntax_error_file_is_skipped(tmp_path):
    _write(tmp_path, "src/quodeq/api/broken.py", "def (:\n")
    assert _scan_src(tmp_path) == []


def test_violation_key_is_relpath_line_kind_module_name(tmp_path):
    _write(tmp_path, "src/quodeq/services/_impl.py", "def f():\n    return 1\n")
    _write(tmp_path, "src/quodeq/api/x.py", "from quodeq.services._impl import f\n")
    (hit,) = _scan_src(tmp_path)
    assert hit.key == "src/quodeq/api/x.py:1:private-module:quodeq.services._impl.f"
    assert check_private_imports.violation_key(hit) == hit.key
    assert "quodeq.services._impl" in check_private_imports.describe(hit)


def test_update_baseline_with_no_violations_writes_header_only(tmp_path, monkeypatch):
    monkeypatch.setattr(check_private_imports, "_scan_src", lambda: [])
    baseline = tmp_path / "private_imports_baseline.txt"

    assert check_private_imports.write_src_baseline(baseline) == 0
    lines = baseline.read_text(encoding="utf-8").splitlines()
    assert lines and all(line.startswith("#") for line in lines)


def test_update_baseline_cli_calls_both_writers(monkeypatch):
    written = {}
    monkeypatch.setattr(check_private_imports, "write_src_baseline", lambda: written.setdefault("src", True) or 0)
    monkeypatch.setattr(check_private_imports, "write_tests_baseline", lambda: written.setdefault("tests", True) or 0)

    assert check_private_imports.main(["--update-baseline"]) == 0
    assert written == {"src": True, "tests": True}


def test_no_new_src_violations():
    baseline = check_private_imports._ratchet.load_baseline(check_private_imports.SRC_BASELINE_PATH)
    new = sorted(set(check_private_imports.collect_src_violations()) - baseline)
    assert new == [], (
        "New private-import violation(s) in src/quodeq. Either "
        "make the name public (drop the underscore) or stop importing it:\n"
        + "\n".join(new)
    )


def test_no_new_tests_violations():
    baseline = check_private_imports._ratchet.load_baseline(check_private_imports.TESTS_BASELINE_PATH)
    new = sorted(set(check_private_imports.collect_tests_violations()) - baseline)
    assert new == [], "New private-import violation(s) in tests/:\n" + "\n".join(new)


def test_src_baseline_has_no_stale_entries():
    current = set(check_private_imports.collect_src_violations())
    stale = sorted(check_private_imports._ratchet.load_baseline(check_private_imports.SRC_BASELINE_PATH) - current)
    assert stale == [], (
        "src baseline lists imports that no longer exist; regenerate with "
        "python tools/check_private_imports.py --update-baseline:\n" + "\n".join(stale)
    )


def test_tests_baseline_has_no_stale_entries():
    current = set(check_private_imports.collect_tests_violations())
    stale = sorted(check_private_imports._ratchet.load_baseline(check_private_imports.TESTS_BASELINE_PATH) - current)
    assert stale == [], (
        "tests baseline lists imports that no longer exist; regenerate with "
        "python tools/check_private_imports.py --update-baseline:\n" + "\n".join(stale)
    )
