"""Rules 2-4 of the private-import gate (tools/_private_imports_strict.py).

Each rule has a positive and a negative case, built in a throwaway
src/quodeq tree so the real tree's state never leaks in.
"""
from __future__ import annotations

from pathlib import Path

import _private_imports_rules as rules
import _private_imports_strict as strict
import check_private_imports


def _write(tmp_path: Path, relpath: str, source: str) -> None:
    f = tmp_path / relpath
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(source, encoding="utf-8")


def _strict(tmp_path: Path) -> list[tuple[str, str, str]]:
    src_root = tmp_path / "src" / "quodeq"
    hits = rules.scan_tree(src_root, src_root, tmp_path, extra=strict.strict_hits)
    return [(h.kind, h.module, h.name) for h in hits]


def _pkg(tmp_path: Path) -> None:
    _write(tmp_path, "src/quodeq/services/__init__.py", "")
    _write(tmp_path, "src/quodeq/services/y.py", "def _helper():\n    return 1\n\n\ndef helper():\n    return 2\n")
    _write(tmp_path, "src/quodeq/services/_impl.py", "def f():\n    return 1\n")


def test_rule2_flags_same_directory_absolute_private_name(tmp_path):
    _pkg(tmp_path)
    _write(tmp_path, "src/quodeq/services/z.py", "from quodeq.services.y import _helper\n")
    assert _strict(tmp_path) == [("private-name", "quodeq.services.y", "_helper")]


def test_rule2_flags_relative_private_name(tmp_path):
    _pkg(tmp_path)
    _write(tmp_path, "src/quodeq/services/z.py", "from .y import _helper\n")
    assert _strict(tmp_path) == [("private-name", ".y", "_helper")]


def test_rule2_allows_public_names_and_private_modules_in_the_package(tmp_path):
    _pkg(tmp_path)
    _write(tmp_path, "src/quodeq/services/z.py",
           "from quodeq.services.y import helper\nfrom . import _impl\nfrom ._impl import f\n")
    assert _strict(tmp_path) == []


def test_rule2_leaves_the_cross_directory_case_to_rule_a(tmp_path):
    _pkg(tmp_path)
    _write(tmp_path, "src/quodeq/api/x.py", "from quodeq.services.y import _helper\n")
    assert _strict(tmp_path) == [("private-name", "quodeq.services.y", "_helper")]


def test_rule3_flags_private_names_in_all(tmp_path):
    _write(tmp_path, "src/quodeq/services/y.py",
           '__all__ = ["_helper", "helper", "__version__"]\n')
    assert _strict(tmp_path) == [("private-export", "__all__", "_helper")]


def test_rule3_ignores_an_all_without_private_names(tmp_path):
    _write(tmp_path, "src/quodeq/services/y.py", '__all__ = ["helper"]\n')
    assert _strict(tmp_path) == []


def test_rule3_flags_private_names_in_an_annotated_all(tmp_path):
    _write(tmp_path, "src/quodeq/services/y.py",
           '__all__: list[str] = ["_helper", "helper"]\n')
    assert _strict(tmp_path) == [("private-export", "__all__", "_helper")]


def test_rule3_ignores_an_annotated_all_without_private_names(tmp_path):
    _write(tmp_path, "src/quodeq/services/y.py",
           '__all__: list[str] = ["helper"]\n')
    assert _strict(tmp_path) == []


def test_rule3_flags_private_names_appended_to_all(tmp_path):
    _write(tmp_path, "src/quodeq/services/y.py",
           '__all__ = ["helper"]\n__all__ += ["_helper"]\n')
    assert _strict(tmp_path) == [("private-export", "__all__", "_helper")]


def test_rule3_ignores_public_names_appended_to_all(tmp_path):
    _write(tmp_path, "src/quodeq/services/y.py",
           '__all__ = ["helper"]\n__all__ += ["other"]\n')
    assert _strict(tmp_path) == []


def test_rule4_flags_private_attribute_through_a_module_alias(tmp_path):
    _pkg(tmp_path)
    _write(tmp_path, "src/quodeq/services/z.py",
           "from quodeq.services import y\nimport quodeq.services.y as yy\nfrom . import y as rel\n\n"
           "a = y._helper()\nb = yy._helper()\nc = rel._helper()\n")
    assert sorted(_strict(tmp_path)) == [
        ("private-attr", ".y", "_helper"),
        ("private-attr", "quodeq.services.y", "_helper"),
        ("private-attr", "quodeq.services.y", "_helper"),
    ]


def test_rule4_ignores_instance_attributes_and_public_attributes(tmp_path):
    _pkg(tmp_path)
    _write(tmp_path, "src/quodeq/services/z.py",
           "from quodeq.services import y\n\n\nclass C:\n"
           "    def m(self, provider):\n        return self._x, provider._jobs, y.helper()\n")
    assert _strict(tmp_path) == []


def test_rule4_flags_dotted_chain_after_a_plain_import(tmp_path):
    _pkg(tmp_path)
    _write(tmp_path, "src/quodeq/services/z.py",
           "import quodeq.services.y\n\na = quodeq.services.y._helper()\n")
    assert _strict(tmp_path) == [("private-attr", "quodeq.services.y", "_helper")]


def test_rule4_ignores_a_public_dotted_chain_after_a_plain_import(tmp_path):
    _pkg(tmp_path)
    _write(tmp_path, "src/quodeq/services/z.py",
           "import quodeq.services.y\n\na = quodeq.services.y.helper()\n")
    assert _strict(tmp_path) == []


def test_src_scan_uses_the_strict_rules(tmp_path, monkeypatch):
    _pkg(tmp_path)
    _write(tmp_path, "src/quodeq/services/z.py", "from .y import _helper\n")
    monkeypatch.setattr(check_private_imports, "SRC_ROOT", tmp_path / "src" / "quodeq")
    monkeypatch.setattr(check_private_imports, "REPO_ROOT", tmp_path)
    assert [h.kind for h in check_private_imports._scan_src()] == ["private-name"]
