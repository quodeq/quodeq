"""Policy for a client-supplied AI binary override (aiCmdPath): syntax, PATH
containment, and provider-name matching.

Split out of api/_evaluation_helpers.py so the rules are reusable outside the
API layer; ``_evaluation_helpers`` re-exports ``ai_cmd_path_error`` for its
own ``validate_ai_cmd_path`` and for ``routes_discovery.py``'s eager check.
"""
from __future__ import annotations

import os.path
import re
import shutil
from collections.abc import Mapping

from quodeq.shared.env_resolve import resolve_env
from quodeq.shared.utils import get_ai_cmd as _get_ai_cmd

# Binary override charset: letters, digits, '.', '_', '-', ':' and path
# separators. No whitespace or shell metacharacters, matching the posture of
# shared.prereqs.SAFE_CMD_TOKEN_RE.
_SAFE_CMD_PATH_RE = re.compile(r"[A-Za-z0-9._/\\:-]+")


def _path_dirs(env: Mapping[str, str] | None = None) -> list[str]:
    """Real (symlink-resolved, case-normalized) directories on the server's PATH."""
    raw = resolve_env(env).get("PATH", "")
    return [os.path.normcase(os.path.realpath(d)) for d in raw.split(os.pathsep) if d]


def ai_cmd_path_error(
    ai_cmd: str | None, ai_cmd_path: str | None, env: Mapping[str, str] | None = None,
) -> str | None:
    """Reason *ai_cmd_path* is not an acceptable binary override for
    provider *ai_cmd*, or None if valid (or absent).

    The aiCmd allow-list exists so the local HTTP API can never spawn an
    arbitrary binary. A free-text override would reopen that, so it must
    (a) contain no shell metacharacters or '..' segments, (b) be absolute
    when it names a path at all, (c) have a basename that starts with the
    provider id (e.g. 'claude-api' or '/opt/bin/claude-max' for 'claude'),
    (d) resolve to an existing executable, and (e) live in a directory on
    the server's PATH. (c) keeps the override an alternate install of the
    allowed CLI, (e) keeps it out of attacker-writable locations like /tmp
    or a downloads folder.

    Pure rules-to-reason form so both the start-evaluation 400 and the
    Settings eager check (GET /api/ai-clients/<id>/cmd-path-check) apply
    the same rules from one place. *env* overrides the PATH lookup and
    defaults to ``os.environ``.
    """
    if not ai_cmd_path:
        return None
    environ = resolve_env(env)
    if not _SAFE_CMD_PATH_RE.fullmatch(ai_cmd_path):
        return "only letters, digits, '.', '_', '-', ':' and path separators are allowed"
    normalized = ai_cmd_path.replace("\\", "/")
    if ".." in normalized.split("/"):
        return "'..' path segments are not allowed"
    if "/" in normalized and not os.path.isabs(ai_cmd_path):
        return "a path must be absolute; otherwise use a bare command name"
    provider = ai_cmd or _get_ai_cmd()
    basename = os.path.basename(normalized)
    if not basename.startswith(provider):
        return f"binary name must start with '{provider}'"
    # The messages below name "the given path" instead of interpolating
    # ai_cmd_path: they reach clients verbatim (start-evaluation 400 and the
    # Settings eager check alike), and no request input is ever reflected
    # back in a response. The reader is looking at the field they typed the
    # path into, so pointing at it loses nothing.
    resolved = shutil.which(ai_cmd_path, path=environ.get("PATH", os.defpath))
    if resolved is None:
        return "the given path was not found or is not executable"
    resolved_dir = os.path.normcase(os.path.realpath(os.path.dirname(os.path.abspath(resolved))))
    if resolved_dir not in _path_dirs(environ):
        return (
            "the given path is not in a directory on PATH; move it to one "
            "(e.g. ~/.local/bin) or add its directory to PATH"
        )
    return None
