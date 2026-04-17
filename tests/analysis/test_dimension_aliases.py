"""Tests for dimension alias expansion."""
from __future__ import annotations


def test_expand_dimension_aliases_single_short():
    from quodeq.analysis._dimension_aliases import expand_dimension_aliases
    assert expand_dimension_aliases("sec") == "security"


def test_expand_dimension_aliases_all_shorts():
    from quodeq.analysis._dimension_aliases import expand_dimension_aliases
    result = expand_dimension_aliases("sec,rel,mnt,perf,flex,ux")
    assert result == "security,reliability,maintainability,performance,flexibility,usability"


def test_expand_dimension_aliases_mixed():
    from quodeq.analysis._dimension_aliases import expand_dimension_aliases
    assert expand_dimension_aliases("security,rel") == "security,reliability"


def test_expand_dimension_aliases_full_names_unchanged():
    from quodeq.analysis._dimension_aliases import expand_dimension_aliases
    assert expand_dimension_aliases("security,reliability") == "security,reliability"


def test_expand_dimension_aliases_passes_through_unknown():
    """Unknown tokens pass through — they get validated downstream."""
    from quodeq.analysis._dimension_aliases import expand_dimension_aliases
    assert expand_dimension_aliases("xyz") == "xyz"


def test_expand_dimension_aliases_strips_whitespace():
    from quodeq.analysis._dimension_aliases import expand_dimension_aliases
    assert expand_dimension_aliases("sec , rel") == "security,reliability"


def test_expand_dimension_aliases_none_returns_none():
    from quodeq.analysis._dimension_aliases import expand_dimension_aliases
    assert expand_dimension_aliases(None) is None


def test_expand_dimension_aliases_empty_returns_empty():
    from quodeq.analysis._dimension_aliases import expand_dimension_aliases
    assert expand_dimension_aliases("") == ""
