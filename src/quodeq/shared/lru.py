"""One bounded LRU mapping for the per-process memo caches.

The fingerprint hash memo (analysis), the precedent memo (context) and the
embedding availability cache (llm_bridge) each need the same thing: a dict
that refreshes an entry's recency on every hit and overwrite, and drops the
least recently used entry once it grows past a capacity. shared/ is the one
layer all three may import, so the type lives here once and is tested once.

No locking inside. Every caller already serialises access under its own
lock; a second lock here would only add an acquisition per operation.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Generic, TypeVar, overload

K = TypeVar("K")
V = TypeVar("V")
D = TypeVar("D")


class LRUDict(Generic[K, V]):
    """Mapping capped at *capacity* entries, evicting the least recently used.

    ``get`` and ``put`` both count as a use, so an overwritten key is as
    fresh as a newly inserted one. ``in`` is a passive probe and leaves
    recency alone. Wraps rather than subclasses ``OrderedDict`` so the only
    ways in are the two that keep recency right.
    """

    __slots__ = ("_data", "capacity")

    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.capacity = capacity
        self._data: OrderedDict[K, V] = OrderedDict()

    @overload
    def get(self, key: K) -> V | None: ...

    @overload
    def get(self, key: K, default: D) -> V | D: ...

    def get(self, key: K, default: D | None = None) -> V | D | None:
        """Value for *key*, refreshed as most recent, or *default* on a miss."""
        try:
            value = self._data[key]
        except KeyError:
            return default
        self._data.move_to_end(key)
        return value

    def put(self, key: K, value: V) -> None:
        """Store *key* as the most recent entry; evict the coldest past capacity."""
        self._data[key] = value
        self._data.move_to_end(key)
        while len(self._data) > self.capacity:
            self._data.popitem(last=False)

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def __len__(self) -> int:
        return len(self._data)

    def clear(self) -> None:
        self._data.clear()
