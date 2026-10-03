"""Repository URL validation and SSRF protection."""

from __future__ import annotations

import re
import urllib.parse
from pathlib import Path

from quodeq.shared.git_errors import NotAGitRepoError
from quodeq.shared.repo import FILE_URL_PREFIX
from quodeq.shared.ssrf import is_private_address
from quodeq.shared.validation import contained_path

_REPO_URL_RE = re.compile(
    r"^(https?://[\w.\-]+/[\w.\-/]+(\.git)?"
    r"|git@[\w.\-]+:[\w.\-/]+(\.git)?"
    r"|ssh://(?:[\w.\-]+@)?[\w.\-]+(?::\d+)?/[\w.\-/]+(\.git)?)$"
)

# IP-like hostnames that must be rejected to prevent SSRF via git clone.
# Covers IPv4 private ranges, IPv6 loopback (::1), IPv6 ULA (fc00::/7), and localhost.
_PRIVATE_HOST_RE = re.compile(
    r"^https?://"
    r"(10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|192\.168\.\d+\.\d+|169\.254\.\d+\.\d+|127\.\d+\.\d+\.\d+"
    r"|localhost"
    r"|\[::1\]|\[fc[0-9a-fA-F]{2}:.*\]|\[fd[0-9a-fA-F]{2}:.*\]|\[fe80:.*\]"
    r")[:/]"
)


_DOT_SEGMENTS = (".", "..")
MESSAGE_LOCAL_OUTSIDE_HOME = "Local repositories must be an absolute file:/// path under your home folder"


def _resolves_to_private(hostname: str) -> bool:
    """Return True if *hostname* resolves to a private/loopback IP address.

    Delegates to the shared SSRF module to avoid duplicating DNS-resolution
    and private-address detection logic.
    """
    return is_private_address(hostname)


def _remote_host(repo_input: str) -> str:
    """Return the host of a format-validated repo URL.

    Handles all supported forms so the private-host check covers them equally:
    ``https://host/path``, ``ssh://[user@]host[:port]/path`` and the scp-like
    ``git@host:path`` form. The SSH forms skip ``_PRIVATE_HOST_RE`` (anchored to ``^https?://``), so without
    this it would reach git clone unguarded.
    """
    if repo_input.startswith(("http", "ssh://")):
        return urllib.parse.urlparse(repo_input).hostname or ""
    if repo_input.startswith("git@"):
        return repo_input[len("git@"):].split(":", 1)[0].strip("[]")
    return ""


def is_valid_repo_url(url: str) -> bool:
    """Return True if *url* matches the expected git repository URL format."""
    return _REPO_URL_RE.match(url) is not None


def validate_local_git_repo(file_url: str) -> None:
    """Accept a ``file://`` URL only for a git repository under the home folder.

    Only the absolute form ``file:///path`` is valid, so what is checked is
    exactly what git reads: the decoded remainder must start with ``/`` and
    its last segment may not be ``.`` or ``..``. The path is resolved
    (symlinks followed) and must sit under ``Path.home()``; it must be a
    worktree (``.git`` present) or a bare repository (``HEAD`` file and
    ``objects`` directory). Pointers inside the repository itself (a ``.git``
    file, ``objects/info/alternates``) are the user's own and are not
    followed or restricted. Messages are fixed: the path is never echoed.
    """
    raw = urllib.parse.unquote(file_url[len(FILE_URL_PREFIX):])
    if not raw.startswith("/") or raw.rstrip("/").rsplit("/", 1)[-1] in _DOT_SEGMENTS:
        raise ValueError(MESSAGE_LOCAL_OUTSIDE_HOME)
    try:
        folder = Path(contained_path(raw, Path.home()))
    except ValueError as exc:
        raise ValueError(MESSAGE_LOCAL_OUTSIDE_HOME) from exc
    if not folder.is_dir():
        raise NotAGitRepoError()
    is_worktree = (folder / ".git").exists()
    is_bare = (folder / "HEAD").is_file() and (folder / "objects").is_dir()
    if not (is_worktree or is_bare):
        raise NotAGitRepoError()


def validate_remote_url(repo_input: str) -> None:
    """Reject malformed / private / DNS-rebinding repository URLs.

    Shared SSRF guard used by both the CLI clone path
    (:func:`quodeq.data.fs.repo_clone.prepare_repository`) and the web API
    registration path (:func:`quodeq.services.evaluation_mixin._register_project`),
    so the two entry points cannot drift apart on what they consider safe.
    Raises ``ValueError`` for any rejected URL.
    """
    if repo_input.startswith(FILE_URL_PREFIX):
        validate_local_git_repo(repo_input)
        return
    if not _REPO_URL_RE.match(repo_input):
        raise ValueError(f"Invalid repository URL format: {repo_input}. Expected: https://github.com/user/repo, ssh://git@github.com/user/repo.git or git@github.com:user/repo.git")
    if _PRIVATE_HOST_RE.match(repo_input):
        raise ValueError("Repository URLs pointing to private/internal addresses are not allowed")
    hostname = _remote_host(repo_input)
    if hostname and _resolves_to_private(hostname):
        raise ValueError("Repository URL resolves to a private/internal address")
