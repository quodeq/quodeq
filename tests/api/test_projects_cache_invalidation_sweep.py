"""Every route that changes the project set invalidates the provider's project cache.

Static: reads the route function's source and requires the call, so a new
mutation route that forgets it fails here instead of in a user's session.
"""
from __future__ import annotations

import inspect

import pytest

from quodeq.api import routes_project_create, routes_project_list, routes_shared_config, routes_shared_pull

_CALL = "invalidate_projects_cache()"
# The pull job hands the bound method to its worker as ``on_done``.
_CALLBACK = "on_done=provider.invalidate_projects_cache"

MUTATION_ROUTES = [
    (routes_project_create.handle_create_project, _CALL),
    (routes_project_list.handle_import_project, _CALL),
    (routes_project_list.handle_delete_project, _CALL),
    (routes_project_list.handle_update_project_path, _CALL),
    (routes_shared_pull.handle_shared_pull, _CALLBACK),
    (routes_shared_config.shared_config_delete, _CALL),
]


@pytest.mark.parametrize("route,expected", MUTATION_ROUTES, ids=lambda v: getattr(v, "__name__", None))
def test_mutation_route_invalidates_projects_cache(route, expected):
    assert expected in inspect.getsource(route), f"{route.__name__} must contain {expected}"
