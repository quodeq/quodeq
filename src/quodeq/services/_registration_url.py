"""Origin-URL helpers for project registration: strip embedded credentials
before a remote URL is persisted or echoed, and read a local clone's
origin remote (already stripped).

Split out of project_registration.py (Task 12).
"""
from __future__ import annotations

import re
from pathlib import Path

from quodeq.services._wiring import remote_origin_url_raw
from quodeq.shared._repo import _looks_like_authority

# Mirrors _SCHEME_RE in quodeq.api._evaluation_helpers. Not imported from
# there: services must not depend on the api layer (no other services module
# does), so this scheme-match pattern is duplicated here rather than layered
# across. _looks_like_authority is imported from shared/_repo.py instead of
# duplicated: it's a pure predicate with no shape coupling to this module,
# and this codebase already imports private helpers from shared._repo
# elsewhere (e.g. data/git_cli.py, shared/utils.py).
_SCHEME_RE = re.compile(r"^(https?://)")


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
    match = _SCHEME_RE.match(url)
    if not match:
        return url
    scheme = match.group(1)
    rest = url[len(scheme):]
    at_pos = rest.rfind("@")
    if at_pos == -1:
        return url
    slash_pos = rest.find("/")
    if -1 < slash_pos < at_pos and _looks_like_authority(rest[:slash_pos]):
        return url
    return scheme + rest[at_pos + 1:]


def _read_origin_remote(repo_dir: Path) -> str | None:
    """Best-effort ``git remote get-url origin`` for a local working copy."""
    origin = remote_origin_url_raw(repo_dir)
    if not origin:
        return None
    return _strip_credentials(origin)
