"""Origin-URL helpers for project registration: strip embedded credentials
before a remote URL is persisted or echoed, and read a local clone's
origin remote (already stripped).

Split out of project_registration.py (Task 12).
"""
from __future__ import annotations

import re
from pathlib import Path

from quodeq.services._wiring import remote_origin_url_raw

# Mirrors _CREDENTIALS_RE in quodeq.api._evaluation_helpers. Not imported from
# there: services must not depend on the api layer (no other services module
# does), so the pattern is duplicated here rather than layered across.
# Userinfo cannot contain an unencoded "/", so excluding it keeps matches
# identical while a failing scan stays linear (no polynomial backtracking
# on inputs like repeated "http://" runs).
_CREDENTIALS_RE = re.compile(r"(https?://)([^/@]+)@")


def _strip_credentials(url: str) -> str:
    """Remove embedded userinfo (``user:pass@`` / ``token@``) from *url*.

    Only applies to scheme'd URLs (``https://user@host/...``). scp-style
    remotes (``git@github.com:org/repo.git``) are left untouched, since the
    leading ``git@`` there is a username convention, not a credential.
    """
    return _CREDENTIALS_RE.sub(r"\1", url)


def _read_origin_remote(repo_dir: Path) -> str | None:
    """Best-effort ``git remote get-url origin`` for a local working copy."""
    origin = remote_origin_url_raw(repo_dir)
    if not origin:
        return None
    return _strip_credentials(origin)
