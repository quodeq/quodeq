"""Machine-readable error-code coverage for GET /api/shared/status
(usability cycle 1, task 6 sweep): the one bare jsonify() tools/
check_error_codes.py (the zero-tolerance gate added in task 6) found under
routes_shared_config.py -- the status payload's reserved, always-present
"error" field now has a matching reserved "code" field alongside it.

Sibling of test_shared_routes_error_codes.py. The ``client`` fixture is
reused, not copied, from tests/api/_routes_shared_fixtures.py.
"""
from __future__ import annotations

from tests.api._routes_shared_fixtures import client  # noqa: F401 -- pytest fixture


def test_shared_status_has_reserved_code_field(client):
    resp = client.get("/api/shared/status")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["error"] is None
    assert body["code"] is None
