"""Use case: connect (validate + clone) a shared results repository.

Extracted from the PUT /api/shared/config route body so the connect-and-
validate business logic is testable without an HTTP request; the route
becomes a thin translation of a ConnectOutcome into one of five response
shapes. Distinct from services/shared_publish.py, which stages an already-
LOCAL project's data into an already-connected clone.
"""
from __future__ import annotations

from dataclasses import dataclass

from quodeq.services.shared_repo import (
    check_repo_format,
    ensure_shared_clone,
    read_state,
    refresh_shared_clone,
    validate_remote_url,
)
from quodeq.services.shared_settings import SharedSettings, write_settings


@dataclass(frozen=True)
class ConnectOutcome:
    """Result of attempting to connect to a shared results repository."""
    status: str  # ok | invalid_url | clone_failed | foreign | unsupported_version
    url: str | None = None
    detail: str = ""  # ValueError text, only set for invalid_url


def connect_shared_repo(url: str) -> ConnectOutcome:
    """Validate, clone (or refresh an existing clone of), and format-check *url*.

    Persists the new setting on success. Moved verbatim from the PUT
    /api/shared/config route body -- the ordering below is load-bearing (see
    test_put_config_rejects_foreign_repo_after_clone and
    test_put_config_reconnect_refreshes_pre_existing_clone) and must not be
    reordered.
    """
    try:
        validate_remote_url(url)
    except ValueError as exc:
        return ConnectOutcome(status="invalid_url", url=url, detail=str(exc))
    # Audit finding A4: reconnecting to a URL whose cache dir is already
    # on disk (a prior connect, possibly stale) must not silently keep
    # serving whatever was last fetched -- ensure_shared_clone below
    # early-returns an existing clone without fetching, so the freshness
    # check has to happen here, before it. refresh_shared_clone acquires
    # clone_lock itself (RLock, so nesting would be safe too, but there
    # is nothing else in this route that needs the lock held around it).
    pre_existing = read_state(url) != "missing"
    repo = ensure_shared_clone(url)
    if repo is None:
        return ConnectOutcome(status="clone_failed", url=url)
    if pre_existing:
        ok, _ = refresh_shared_clone(url)  # best effort; failure just leaves the pre-existing clone as-is, reason already logged internally
    # Format validation only makes sense once the clone actually exists,
    # so it runs AFTER ensure_shared_clone, not before -- a foreign or
    # too-new repo must never reach write_settings (that would connect
    # the UI to a repo every subsequent /api/shared/* route then 409s
    # on). "empty" (never published into) is a legitimate first-connect
    # state and is accepted here same as "ok".
    fmt = check_repo_format(repo)
    if fmt == "foreign":
        return ConnectOutcome(status="foreign", url=url)
    if fmt == "unsupported_version":
        return ConnectOutcome(status="unsupported_version", url=url)
    write_settings(SharedSettings(url=url))
    return ConnectOutcome(status="ok", url=url)
