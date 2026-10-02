"""DELETE /api/projects/<p> drops the provider's project cache."""
from __future__ import annotations

from tests.api._routes_project_list_fixtures import app, client, provider  # noqa: F401


def test_delete_invalidates_cache_once(client, provider):
    provider.cache_invalidated = 0
    provider.invalidate_projects_cache = lambda: setattr(provider, "cache_invalidated", provider.cache_invalidated + 1)
    assert client.delete("/api/projects/demo?confirm=true").status_code == 200
    assert provider.cache_invalidated == 1
