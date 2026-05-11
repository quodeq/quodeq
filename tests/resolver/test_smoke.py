"""Smoke tests: dependencies importable, resolver package importable."""

def test_tree_sitter_importable():
    import tree_sitter  # noqa: F401


def test_tree_sitter_language_pack_importable():
    import tree_sitter_language_pack  # noqa: F401


def test_python_grammar_loads():
    from tree_sitter_language_pack import get_language
    lang = get_language("python")
    assert lang is not None


def test_resolver_package_importable():
    import quodeq.resolver  # noqa: F401
