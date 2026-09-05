"""Repository URL helpers — pure string/path logic only.

Anything that shells out to git lives in ``data/git_cli.py``; this module
stays importable from the core-only ``shared`` layer.
"""
from __future__ import annotations

from pathlib import Path


def is_repo_url(repo_input: str) -> bool:
    """Return True if the input looks like a remote repository URL.

    Raises ValueError for cleartext ``http://`` URLs to enforce encrypted
    transport for credential safety.
    """
    if repo_input.startswith("http://"):
        raise ValueError(
            "Cleartext HTTP repository URLs are rejected to protect credentials. "
            "Use https:// or git@ instead."
        )
    return repo_input.startswith(("https://", "git@"))


def project_name_from_repo(repo: str) -> str:
    """Extract a human-readable project name from a repo path or URL."""
    if is_repo_url(repo):
        return repo.split("/")[-1].replace(".git", "")
    return Path(repo).resolve().name


def _looks_like_authority(candidate: str) -> bool:
    """Return True if ``candidate`` is a plausible ``host[:port]`` authority.

    Deliberately strict: a bare single-label name is rejected so that an
    ambiguous URL falls to the credential-stripping branch rather than the
    leaking one.
    """
    host, sep, port = candidate.partition(":")
    if sep and not port.isdigit():
        return False
    if not all(c.isalnum() or c in "-._~[]" for c in host):
        return False
    return "." in host or host.startswith("[") or host == "localhost"


def _strip_userinfo(url: str) -> str:
    """Drop any embedded userinfo (``user:token@host``, ``git@host``) from ``url``.

    ``url`` has already had its scheme stripped, so the authority starts at
    position 0. RFC 3986 ends userinfo at the LAST "@" of the authority, so
    the search runs from the right: a password containing "@"
    ("user:p@ss@host") would otherwise leave the tail of the credential in
    the normalized value.

    A "/" before that "@" usually means the authority already ended and the
    "@" belongs to a path segment ("host/~user@host/repo") -- but only when
    the text before that "/" is itself a plausible host. Real credentials
    (base64-derived tokens, JWTs, CI PATs) often contain a literal "/", and
    bounding the search by the first "/" then hides the real "@" and lets
    the whole credential through unstripped.
    """
    at_pos = url.rfind("@")
    if at_pos == -1:
        return url
    slash_pos = url.find("/")
    if -1 < slash_pos < at_pos and _looks_like_authority(url[:slash_pos]):
        return url
    return url[at_pos + 1 :]


def normalize_remote_url(url: str) -> str | None:
    """Fold equivalent git remote URL forms into one canonical form.

    Normalization maps these equivalent forms to a single canonical form:
      - ``git@github.com:owner/repo.git`` -> ``github.com/owner/repo``
      - ``https://github.com/owner/repo.git`` -> ``github.com/owner/repo``
      - ``https://github.com/owner/repo`` -> ``github.com/owner/repo``
      - ``ssh://git@github.com/owner/repo.git`` -> ``github.com/owner/repo``

    Trailing ``.git`` is stripped. Leading ``https://`` / ``ssh://`` / ``git@``
    is stripped. The colon in ``git@host:path`` form is converted to ``/``.
    Non-standard ports (e.g. ``host:22/path``) are not supported.
    Returns ``None`` for an empty/blank input.
    """
    url = (url or "").strip()
    if not url:
        return None

    # Strip known scheme prefixes
    if url.startswith("https://"):
        url = url[len("https://"):]
    elif url.startswith("ssh://"):
        url = url[len("ssh://"):]

    url = _strip_userinfo(url)

    # Convert git@host:path form to host/path.
    # First colon splits host from path when path isn't numeric (port).
    if ":" in url:
        head, _sep, tail = url.partition(":")
        if tail and not tail[:1].isdigit():
            url = f"{head}/{tail}"

    if url.endswith(".git"):
        url = url[:-4]
    url = url.rstrip("/")
    return url or None
