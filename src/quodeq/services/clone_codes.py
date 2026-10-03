"""Wire codes and HTTP statuses for a failed project clone.

Shared by the create route (synchronous failures) and the clone job (the
status slot's ``code``). API contract: do not rename a code.
"""
from __future__ import annotations

from http import HTTPStatus

from quodeq.shared.git_errors import GitFailureKind

CODE_CLONE_UNKNOWN = "CLONE_UNKNOWN"
CODE_CLONE_TIMEOUT = "CLONE_TIMEOUT"
CODE_HOST_KEY_UNVERIFIED = "HOST_KEY_UNVERIFIED"
CODE_GIT_MISSING = "GIT_MISSING"

# GitFailureKind -> (wire code, HTTP status) for a failed clone in POST /api/projects.
CLONE_CODES: dict[GitFailureKind, tuple[str, HTTPStatus]] = {
    GitFailureKind.AUTH_REQUIRED: ("AUTH_REQUIRED", HTTPStatus.BAD_REQUEST),
    GitFailureKind.HOST_KEY: (CODE_HOST_KEY_UNVERIFIED, HTTPStatus.BAD_REQUEST),
    GitFailureKind.NOT_FOUND: ("REPO_NOT_FOUND", HTTPStatus.NOT_FOUND),
    GitFailureKind.DEST_EXISTS: ("DEST_EXISTS", HTTPStatus.CONFLICT),
    GitFailureKind.NETWORK: ("NETWORK_ERROR", HTTPStatus.BAD_GATEWAY),
    GitFailureKind.TIMEOUT: (CODE_CLONE_TIMEOUT, HTTPStatus.GATEWAY_TIMEOUT),
    GitFailureKind.DISK: ("DISK_ERROR", HTTPStatus.INSUFFICIENT_STORAGE),
    GitFailureKind.GIT_MISSING: (CODE_GIT_MISSING, HTTPStatus.INTERNAL_SERVER_ERROR),
    GitFailureKind.UNKNOWN: (CODE_CLONE_UNKNOWN, HTTPStatus.BAD_GATEWAY),
}


def clone_code_for(kind: GitFailureKind) -> tuple[str, HTTPStatus]:
    """The (wire code, HTTP status) for *kind*, ``CLONE_UNKNOWN`` when unmapped."""
    return CLONE_CODES.get(kind, (CODE_CLONE_UNKNOWN, HTTPStatus.BAD_GATEWAY))
