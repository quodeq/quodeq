"""Contract of ``LRUDict``, the one bounded LRU behind the per-process memos.

``HashCache`` (analysis), the precedent memo (context) and
``EmbeddingAvailabilityCache`` (llm_bridge) all delegate eviction and
recency to this type, so the generic rules are pinned once here: a hit and
an overwrite both refresh recency, an insert past capacity drops the least
recently used entry, ``None`` is a real value, and ``in`` is a passive
probe. The adopters' own tests only check that their capacity is wired.
"""
from __future__ import annotations

import pytest

from quodeq.shared.lru import LRUDict


def test_get_returns_default_on_miss() -> None:
    cache: LRUDict[str, int] = LRUDict(2)
    assert cache.get("a") is None
    assert cache.get("a", -1) == -1
    assert "a" not in cache
    assert len(cache) == 0


def test_put_past_capacity_evicts_least_recently_used() -> None:
    cache: LRUDict[str, int] = LRUDict(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)
    assert "a" not in cache
    assert cache.get("b") == 2
    assert cache.get("c") == 3
    assert len(cache) == 2


def test_get_hit_refreshes_recency() -> None:
    cache: LRUDict[str, int] = LRUDict(2)
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") == 1  # a is now the most recent, b the coldest
    cache.put("c", 3)
    assert "b" not in cache
    assert cache.get("a") == 1


def test_put_on_existing_key_refreshes_recency() -> None:
    """The bug behind the shared type: an overwrite must count as a use."""
    cache: LRUDict[str, int] = LRUDict(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("a", 10)  # overwrite, not insert: a is now the most recent
    cache.put("c", 3)
    assert "b" not in cache
    assert cache.get("a") == 10
    assert len(cache) == 2


def test_none_is_a_real_value() -> None:
    cache: LRUDict[str, str | None] = LRUDict(1)
    cache.put("a", None)
    assert "a" in cache
    assert cache.get("a") is None
    sentinel = object()
    assert cache.get("a", sentinel) is None  # stored None, not the default
    assert cache.get("b", sentinel) is sentinel


def test_contains_does_not_refresh_recency() -> None:
    cache: LRUDict[str, int] = LRUDict(2)
    cache.put("a", 1)
    cache.put("b", 2)
    assert "a" in cache  # a passive probe leaves a as the coldest
    cache.put("c", 3)
    assert "a" not in cache
    assert "b" in cache


def test_clear_empties_the_cache() -> None:
    cache: LRUDict[str, int] = LRUDict(2)
    cache.put("a", 1)
    cache.clear()
    assert len(cache) == 0
    assert cache.get("a") is None


def test_rejects_capacity_below_one() -> None:
    with pytest.raises(ValueError):
        LRUDict(0)
