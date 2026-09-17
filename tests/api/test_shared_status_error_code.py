"""GET /api/shared/status keeps its reserved error slot without a code.

The status payload's always-present ``"error"`` field is a reserved slot the
UI binds to without existence checks, not an error response, so it carries no
``"code"``: tools/check_error_codes.py exempts a dict literal whose
``"error"`` value is ``None`` (final-review item 9). A meaningless
``"code": None`` was added to satisfy the gate's earlier false positive and
is removed again here.

Sibling of test_shared_routes_error_codes.py. The ``client`` fixture is
reused, not copied, from tests/api/_routes_shared_fixtures.py.
"""
from __future__ import annotations

from tests.api._routes_shared_fixtures import client  # noqa: F401 -- pytest fixture


def test_shared_status_keeps_the_reserved_error_slot_without_a_code(client):
    resp = client.get("/api/shared/status")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["error"] is None
    assert "code" not in body
