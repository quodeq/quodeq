"""Project-set mutations drop the provider's project cache, observed at runtime.

The static sweep (test_projects_cache_invalidation_sweep.py) proves every
mutation route names the call; these prove the call actually runs once.
"""
from __future__ import annotations

import pytest

from tests.api._project_import_fixtures import _make_zip, _patch_home, _post_zip
from tests.api._routes_project_list_fixtures import app, client, provider  # noqa: F401


@pytest.fixture()
def spy(provider):
    provider.cache_invalidated = 0
    provider.invalidate_projects_cache = lambda: setattr(provider, "cache_invalidated", provider.cache_invalidated + 1)
    return provider


def test_delete_invalidates_cache_once(client, spy):
    assert client.delete("/api/projects/demo?confirm=true").status_code == 200
    assert spy.cache_invalidated == 1


def test_import_invalidates_cache_once(client, spy, tmp_path):
    with _patch_home(tmp_path.resolve()):
        resp = _post_zip(client, _make_zip())
    assert resp.status_code == 200, resp.get_json()
    assert spy.cache_invalidated == 1


def test_relocate_invalidates_cache_once(client, spy, tmp_path):
    target = tmp_path / "relocated"
    target.mkdir()
    assert client.patch("/api/projects/demo/path", json={"path": str(target)}).status_code == 200
    assert spy.cache_invalidated == 1
