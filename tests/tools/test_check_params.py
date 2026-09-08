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
