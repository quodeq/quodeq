"""Every route that changes the project set invalidates the provider's project cache.

Static, over the REAL route map: every POST/PUT/PATCH/DELETE rule under
``/api/projects`` or ``/api/shared/`` must either name
``invalidate_projects_cache`` (in its view function or in a function the view
delegates to by name) or be listed in ``EXEMPT`` with the reason it does not
change the project set. A new mutation route that is neither fails here
instead of in a user's session. The runtime counterparts live in
test_projects_cache_delete.py.
"""
from __future__ import annotations

import functools
import inspect

import pytest

from quodeq.api import routes_project_clone, routes_project_create, routes_project_list, routes_shared_config, routes_shared_pull
from quodeq.api.app import create_app

_NAME = "invalidate_projects_cache"
_CALL = "invalidate_projects_cache()"
# The pull job hands the bound method to its worker as ``on_done``.
_CALLBACK = "on_done=provider.invalidate_projects_cache"
_MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_PREFIXES = ("/api/projects", "/api/shared/")

EXEMPT = {
    "shared_publish_start": "pushes a local project to the team repository; the local project set is unchanged",
    "grade_explain_draft": "a read-only preview of a grade under draft parameters; POST only to carry the body",
    "put_standards_overrides": "stores per-project standard overrides read by the scoring routes, not the project list",
    "put_standards_visibility": "stores which standards a project shows, read by the scoring routes, not the project list",
    "shared_config_put": "starts the connect job, which fills the team listing (its own cache), not the local projects",
    "shared_refresh": "starts the refresh job, which updates the team listing (its own cache), not the local projects",
}

MUTATION_ROUTES = [
    (routes_project_create.handle_create_project, _CALL),
    (routes_project_clone.start_clone_job, _CALLBACK),
    (routes_project_list.handle_import_project, _CALL),
    (routes_project_list.handle_delete_project, _CALL),
    (routes_project_list.handle_update_project_path, _CALL),
    (routes_shared_pull.handle_shared_pull, _CALLBACK),
    (routes_shared_config.shared_config_delete, _CALL),
]


def _unwrap(fn):
    """Peel ``functools.partial`` and ``functools.wraps`` layers down to the defined function."""
    while True:
        if isinstance(fn, functools.partial):
            fn = fn.func
        elif hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        else:
            return fn


def _source(fn) -> str:
    try:
        return inspect.getsource(fn)
    except (OSError, TypeError):
        return ""


def _delegates(fn) -> list:
    """The functions *fn* references by name (globals and closure cells)."""
    refs = inspect.getclosurevars(fn)
    names = {**refs.globals, **refs.nonlocals}
    return [_unwrap(v) for v in names.values() if inspect.isfunction(_unwrap(v))]


def _invalidates(view) -> bool:
    fn = _unwrap(view)
    return any(_NAME in _source(f) for f in [fn, *_delegates(fn)])


def _mutation_endpoints() -> dict:
    app = create_app(test_config={"TESTING": True})
    return {
        rule.endpoint: app.view_functions[rule.endpoint]
        for rule in app.url_map.iter_rules()
        if rule.methods & _MUTATING and rule.rule.startswith(_PREFIXES)
    }


_ENDPOINTS = _mutation_endpoints()


@pytest.mark.parametrize("endpoint", sorted(_ENDPOINTS))
def test_mutation_route_invalidates_or_is_exempt(endpoint):
    if endpoint in EXEMPT:
        return
    assert _invalidates(_ENDPOINTS[endpoint]), (
        f"{endpoint} mutates under /api/projects or /api/shared/ but never calls {_NAME}; "
        "call it, or add it to EXEMPT with the reason the project set is unchanged"
    )


def test_exemptions_name_live_routes_with_reasons():
    assert set(EXEMPT) <= set(_ENDPOINTS), f"stale exemptions: {set(EXEMPT) - set(_ENDPOINTS)}"
    assert all(reason.strip() for reason in EXEMPT.values())


def test_sweep_sees_the_known_mutation_routes():
    known = {"create_project", "import_project_route", "delete_project", "update_project_path",
             "shared_pull", "shared_config_delete"}
    assert known <= set(_ENDPOINTS)
    assert all(_invalidates(_ENDPOINTS[e]) for e in known)


def test_a_route_without_the_call_is_caught():
    def new_mutation_route():
        return "changed the project set"

    assert not _invalidates(new_mutation_route)


@pytest.mark.parametrize("route,expected", MUTATION_ROUTES, ids=lambda v: getattr(v, "__name__", None))
def test_mutation_route_invalidates_projects_cache(route, expected):
    assert expected in inspect.getsource(route), f"{route.__name__} must contain {expected}"
