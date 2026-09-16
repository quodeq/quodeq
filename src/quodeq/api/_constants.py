"""Constants shared by the API route modules."""
# House-standard, and it also keeps this import-less module indexed by
# core/checks/framework_deps (edge-keyed; see the follow-up on ImportGraph.files).
from __future__ import annotations

# Machine-readable ``code`` values for ``helpers.error_response``. The UI
# branches on them, so the strings are wire contract.
ERROR_CODE_BAD_REQUEST = "bad_request"
ERROR_CODE_NOT_FOUND = "not_found"
ERROR_CODE_FORBIDDEN = "forbidden"
