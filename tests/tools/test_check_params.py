"""Unit tests for tools/check_params.py: parameter counting and qualnames."""
from __future__ import annotations

import ast
import textwrap

import check_params


def _functions(src: str) -> dict[str, int]:
    tree = ast.parse(textwrap.dedent(src))
    return {
        qual: check_params.param_count(fn, is_method=is_method)
        for qual, fn, is_method in check_params.iter_functions(tree)
    }


def test_counts_positional_keyword_only_varargs_and_kwargs():
    counts = _functions("""
        def f(a, b, /, c, *args, d, e=1, **kw):
            pass
    """)
    assert counts == {"f": 7}


def test_method_self_and_cls_are_not_counted():
    counts = _functions("""
        class Foo:
            def m(self, a, b):
                pass
            @classmethod
            def c(cls, a):
                pass
            @staticmethod
            def s(a, b, c):
                pass
    """)
    assert counts == {"Foo.m": 2, "Foo.c": 1, "Foo.s": 3}


def test_nested_function_qualname_and_no_self_stripping():
    counts = _functions("""
        class Foo:
            def m(self):
                def inner(self, x):
                    pass
        def outer():
            async def inner(a, b):
                pass
    """)
    assert counts == {"Foo.m": 0, "Foo.m.inner": 2, "outer": 0, "outer.inner": 2}


def test_function_inside_class_level_if_is_still_a_method():
    counts = _functions("""
        class Foo:
            if True:
                def m(self, a):
                    pass
    """)
    assert counts == {"Foo.m": 1}


def test_violation_key_ignores_count():
    assert check_params.violation_key(("src/quodeq/x.py", "Foo.m", 9)) == "src/quodeq/x.py:Foo.m"


def test_scan_roots_include_tools():
    assert check_params.REPO_ROOT / "tools" in check_params.SCAN_ROOTS


def test_scan_walks_tools_with_repo_relative_keys(tmp_path, monkeypatch):
    src = tmp_path / "src" / "quodeq"
    src.mkdir(parents=True)
    (src / "ok.py").write_text("def narrow(a, b):\n    pass\n", encoding="utf-8")
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "helper.py").write_text(
        "def wide(a, b, c, d, e, f):\n    pass\n", encoding="utf-8",
    )
    monkeypatch.setattr(check_params, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(check_params, "SCAN_ROOTS", (src, tools))

    assert check_params._scan() == [("tools/helper.py", "wide", 6)]
    assert check_params.collect_violations() == ["tools/helper.py:wide"]


def test_update_baseline_with_no_violations_writes_header_only(tmp_path, monkeypatch):
    monkeypatch.setattr(check_params, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(check_params, "SCAN_ROOTS", ())
    baseline = tmp_path / "param_baseline.txt"

    assert check_params.write_baseline(baseline) == 0
    lines = baseline.read_text(encoding="utf-8").splitlines()
    assert lines and all(line.startswith("#") for line in lines)
    assert check_params.load_baseline(baseline) == set()
