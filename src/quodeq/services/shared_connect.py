"""Use case: connect (validate + clone) a shared results repository.

Extracted from the PUT /api/shared/config route body so the connect-and-
validate business logic is testable without an HTTP request; the route
becomes a thin translation of a ConnectOutcome into one of five response
shapes. Distinct from services/shared_publish.py, which stages an already-
LOCAL project's data into an already-connected clone.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.services.shared_repo import (
    RepoFormat,
    check_repo_format,
    ensure_shared_clone,
    read_state,
    refresh_shared_clone,
    validate_remote_url,
)
from quodeq.services.shared_settings import SharedSettings, write_settings


class ConnectStatus(StrEnum):
    """The two connect outcomes that never reach ``check_repo_format``.

    ``ConnectOutcome.status`` also carries ``RepoFormat.OK`` /
    ``RepoFormat.FOREIGN`` / ``RepoFormat.UNSUPPORTED_VERSION`` once a clone
    exists; these two cover the earlier failures (bad URL, clone itself
    failed) that never get that far.
    """

    INVALID_URL = "invalid_url"
    CLONE_FAILED = "clone_failed"


@dataclass(frozen=True)
class ConnectOutcome:
    """Result of attempting to connect to a shared results repository."""
    status: RepoFormat | ConnectStatus
    url: str | None = None
    detail: str = ""  # ValueError text, only set for invalid_url


def connect_shared_repo(url: str, *, log: LogSink = NULL_LOG) -> ConnectOutcome:
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
        return ConnectOutcome(status=ConnectStatus.INVALID_URL, url=url, detail=str(exc))
    # Reconnecting to a URL whose cache dir is already
    # on disk (a prior connect, possibly stale) must not silently keep
    # serving whatever was last fetched -- ensure_shared_clone below
    # early-returns an existing clone without fetching, so the freshness
    # check has to happen here, before it. refresh_shared_clone acquires
    # clone_lock itself (RLock, so nesting would be safe too, but there
    # is nothing else in this route that needs the lock held around it).
    pre_existing = read_state(url) != RepoFormat.MISSING
    repo = ensure_shared_clone(url)
    if repo is None:
        return ConnectOutcome(status=ConnectStatus.CLONE_FAILED, url=url)
    if pre_existing:
        refresh_shared_clone(url)  # best effort; failure just leaves the pre-existing clone as-is, reason already logged internally
    # Format validation only makes sense once the clone actually exists,
    # so it runs AFTER ensure_shared_clone, not before -- a foreign or
    # too-new repo must never reach write_settings (that would connect
    # the UI to a repo every subsequent /api/shared/* route then 409s
    # on). "empty" (never published into) is a legitimate first-connect
    # state and is accepted here same as "ok".
    fmt = check_repo_format(repo)
    if fmt == RepoFormat.FOREIGN:
        return ConnectOutcome(status=RepoFormat.FOREIGN, url=url)
    if fmt == RepoFormat.UNSUPPORTED_VERSION:
        return ConnectOutcome(status=RepoFormat.UNSUPPORTED_VERSION, url=url)
    write_settings(SharedSettings(url=url), log=log)
    return ConnectOutcome(status=RepoFormat.OK, url=url)
