"""Origin-URL helpers for project registration: strip embedded credentials
before a remote URL is persisted or echoed, and read a local clone's
origin remote (already stripped).

Split out of project_registration.py (Task 12).
"""
from __future__ import annotations

from pathlib import Path

from quodeq.services.wiring import remote_origin_url_raw
from quodeq.shared.repo import split_userinfo



def _strip_credentials(url: str) -> str:
    """Remove embedded userinfo (``user:pass@`` / ``token@``) from *url*.

    Only applies to scheme'd URLs (``https://user@host/...``). scp-style
    remotes (``git@github.com:org/repo.git``) are left untouched, since the
    leading ``git@`` there is a username convention, not a credential.

    Userinfo ends at the LAST "@" of the authority (RFC 3986), so the search
    runs from the right. A "/" before that "@" usually means the authority
    already ended and the "@" belongs to a path segment -- but only when the
    text before that "/" is itself a plausible host. Real credentials
    (base64-derived tokens, JWTs, CI PATs) often contain a literal "/", and
    bounding the search by the first "/" would then hide the real "@" and
    let the whole credential through unstripped.
    """
    parts = split_userinfo(url)
    if parts is None:
        return url
    scheme, after = parts
    return scheme + after


def _read_origin_remote(repo_dir: Path) -> str | None:
    """Best-effort ``git remote get-url origin`` for a local working copy."""
    origin = remote_origin_url_raw(repo_dir)
    if not origin:
        return None
    return _strip_credentials(origin)
