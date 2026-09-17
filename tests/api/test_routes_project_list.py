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


def test_export_project_rejects_invalid_project_name(client):
    resp = client.get("/api/projects/../export")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "INVALID_INPUT"


class TestUpdateProjectPathValidation:
    """finding 5926: update_project_path's distinct failure modes (invalid
    URL, non-directory target, missing project) get their own message
    instead of a blanket "Project not found" 404 for all of them."""

    def test_repo_url_rejected_before_reaching_the_provider(self, client, provider):
        resp = client.patch(
            "/api/projects/my-proj/path", json={"path": "https://github.com/foo/bar"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_INPUT"
        assert "my-proj" not in provider.updated_paths

    def test_cleartext_http_url_names_the_reason(self, client):
        resp = client.patch(
            "/api/projects/my-proj/path", json={"path": "http://github.com/foo/bar"},
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["code"] == "INVALID_INPUT"
        assert "cleartext" in body["error"].lower()

    def test_non_directory_target_is_invalid_input_not_not_found(self, client, tmp_path):
        target = tmp_path / "does-not-exist"
        resp = client.patch("/api/projects/my-proj/path", json={"path": str(target)})
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_INPUT"

    def test_missing_project_is_still_not_found_once_path_is_valid(self, client, provider, tmp_path):
        provider.update_project_path = lambda *a: False
        resp = client.patch("/api/projects/my-proj/path", json={"path": str(tmp_path)})
        assert resp.status_code == 404
        assert resp.get_json()["code"] == "NOT_FOUND"
