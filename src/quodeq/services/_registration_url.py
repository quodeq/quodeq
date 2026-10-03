"""Origin-URL helpers for project registration: strip embedded credentials
before a remote URL is persisted or echoed, and read a local clone's
origin remote (already stripped).

Split out of project_registration.py.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.services.wiring import remote_origin_url_raw
from quodeq.shared.repo import split_userinfo


def strip_credentials(url: str) -> str:
    """Remove embedded userinfo (``user:pass@`` / ``token@``) from *url*.

    Only applies to scheme'd URLs (``https://user@host/...``). scp-style
    remotes (``git@github.com:org/repo.git``) are left untouched, since the
    leading ``git@`` there is a username convention, not a credential.
    ``split_userinfo`` documents how the credential boundary is found.
    """
    parts = split_userinfo(url)
    if parts is None:
        return url
    scheme, after = parts
    return scheme + after


def read_origin_remote(repo_dir: Path) -> str | None:
    """Best-effort ``git remote get-url origin`` for a local working copy."""
    origin = remote_origin_url_raw(repo_dir)
    if not origin:
        return None
    return strip_credentials(origin)
