"""Tests for GET /api/projects pagination slicing behavior.

Shared fixtures (_FakeProvider/provider/app/client) live in
tests/api/_routes_project_list_fixtures.py.
"""
from __future__ import annotations

from tests.api._routes_project_list_fixtures import (  # noqa: F401 -- app/client/provider are pytest fixtures
    app,
    client,
    provider,
)


class _CountingList(list):
    """list subclass that counts __getitem__ (slice) calls across the whole
    slice chain, scoped to this one instance tree -- never patches the
    global list type.

    Plain ``list`` slicing always returns a bare ``list``, even from a
    subclass, so a naive per-instance counter would only ever see the
    *first* slice in a chain: ``a[x:][:y]`` re-slices a plain list the
    counter has no visibility into. To actually distinguish "one bounded
    slice" from "two sequential slices" we re-wrap slice results in the
    same counting class, sharing one counter across the chain.
    """

    def __init__(self, *a, counter: list[int] | None = None, **kw):
        super().__init__(*a, **kw)
        self._counter = counter if counter is not None else [0]

    def __getitem__(self, item):
        self._counter[0] += 1
        result = super().__getitem__(item)
        if isinstance(item, slice):
            return _CountingList(result, counter=self._counter)
        return result

    @property
    def getitem_calls(self) -> int:
        return self._counter[0]


def test_pagination_slices_the_project_list_exactly_once(client, provider):
    """One slice op regardless of offset/limit combination -- not two sequential
    slices, which each copy up to O(n) elements."""
    from quodeq.core.types import ProjectEntry

    entries = _CountingList([
        ProjectEntry(id=f"p{i}", name=f"p{i}") for i in range(50)
    ])
    provider.projects = entries

    resp = client.get("/api/projects?offset=10&limit=5")

    assert resp.status_code == 200
    body = resp.get_json()
    assert [p["id"] for p in body["projects"]] == [f"p{i}" for i in range(10, 15)]
    assert entries.getitem_calls == 1, (
        f"expected exactly one slice, got {entries.getitem_calls}"
    )
