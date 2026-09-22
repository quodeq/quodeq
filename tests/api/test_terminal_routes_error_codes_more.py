"""More machine-readable error-code coverage for terminal_routes.py
(usability cycle 1, task 6 sweep): the one bare jsonify() tools/
check_error_codes.py (the zero-tolerance gate added in task 6) found under
terminal_routes.py -- POST /api/terminal/open's "path is required" 400.

Sibling of test_terminal_routes_error_codes.py. The ``app``/``_FakeManager``
fixtures are reused, not copied, from test_terminal_routes.py.
"""
from __future__ import annotations

from tests.api.test_terminal_routes import app  # noqa: F401 -- pytest fixture

_ORIGIN = {"Origin": "http://localhost"}


def test_open_missing_path_has_code(app):
    c = app.test_client()
    r = c.post("/api/terminal/open", json={}, headers=_ORIGIN, base_url="http://localhost")
    assert r.status_code == 400
    assert r.get_json()["code"] == "MISSING_PARAM"
