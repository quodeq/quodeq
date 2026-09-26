"""Constants shared by the API route modules."""
# House-standard, and it also keeps this import-less module indexed by
# core/checks/framework_deps (edge-keyed; see the follow-up on ImportGraph.files).
from __future__ import annotations

# Machine-readable ``code`` values for ``helpers.error_response``. The UI
# branches on them, so the strings are wire contract.
ERROR_CODE_BAD_REQUEST = "bad_request"
ERROR_CODE_NOT_FOUND = "not_found"
ERROR_CODE_FORBIDDEN = "forbidden"
# Same spelling as services IMPORT_STATUS_CONFLICT, but a different contract:
# this is the error_response ``code``, that is the import result ``status``.
ERROR_CODE_CONFLICT = "conflict"

# request.args values are always str, never bool, so boolean query-param
# flags (``?confirm=true``, ``?discard=true``, ``?dryRun=1``, ``?refresh=1``)
# compare against these string forms.
QUERY_FLAG_TRUE = "true"
QUERY_FLAG_TRUE_NUMERIC = "1"
QUERY_FLAG_TRUTHY = (QUERY_FLAG_TRUE_NUMERIC, QUERY_FLAG_TRUE)  # accepted truthy spellings

# Machine-readable ``code`` values for the evaluations/findings/assistant/
# shared-mirror routes' own {"error", "code"} shape. A distinct, SCREAMING_
# SNAKE wire vocabulary from the lower-case ERROR_CODE_* family above (those
# routes predate the standards_* CRUD split and never adopted it) -- the
# values are API contract and must not change.
CODE_INVALID_INPUT = "INVALID_INPUT"
CODE_INVALID_PARAM = "INVALID_PARAM"
CODE_MISSING_PARAM = "MISSING_PARAM"
CODE_INVALID_REPO = "INVALID_REPO"
CODE_INVALID_CLONE_DEST = "INVALID_CLONE_DEST"
# routes_project_create's discipline field type check.
CODE_INVALID_DISCIPLINE = "INVALID_DISCIPLINE"
CODE_NOT_FOUND = "NOT_FOUND"
# The app-wide fallback handler's code for an exception no route caught
# (api/_error_handlers.py). Some narrowed route catches already answer this
# same string as a bare literal for their own realistic failure types
# (routes_runs.py, _scores_routes.py, routes_compare.py, _index_routes.py,
# routes_shared_mirrors.py) -- both are "internal error, 500" to the client.
CODE_INTERNAL_ERROR = "INTERNAL_ERROR"
CODE_PROJECT_EXISTS = "PROJECT_EXISTS"  # 409 for a project already registered or imported
CODE_GONE = "GONE"  # the run a job pointed at has no directory any more
CODE_FORBIDDEN = "FORBIDDEN"
CODE_UNKNOWN_SESSION = "UNKNOWN_SESSION"
CODE_NO_ACTIVE_WORKTREE = "NO_ACTIVE_WORKTREE"
# routes_shared_pull's optional "action" field (copy|replace) on a pull collision.
CODE_INVALID_ACTION = "INVALID_ACTION"
MESSAGE_UNKNOWN_SESSION = "unknown session"
MESSAGE_INVALID_PROJECT_NAME = "Invalid project name"  # 400 for a malformed <project> segment
# No shared results repository is configured (shared routes, assistant shared sessions).
CODE_NO_SHARED_REPO = "NO_SHARED_REPO"
MESSAGE_NO_SHARED_REPO = "no shared repository configured"

# Hard cap on a findings-listing page, local and shared-clone mirrors alike
# (routes_findings.py, routes_shared_findings_mirrors.py).
MAX_FINDINGS_LIST_LIMIT = 5000
