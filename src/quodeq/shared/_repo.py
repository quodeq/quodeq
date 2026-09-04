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

    # Strip any embedded userinfo (e.g. user:token@host or git@host) from the
    # authority component -- everything up to the first /. RFC 3986 ends
    # userinfo at the LAST "@" in the authority, not the first: a password
    # containing "@" ("user:p@ss@host") would otherwise leave the tail of the
    # credential ("ss@host") in the normalized value.
    slash_pos = url.find("/")
    authority_end = slash_pos if slash_pos != -1 else len(url)
    at_pos = url.rfind("@", 0, authority_end)
    if at_pos != -1:
        url = url[at_pos + 1 :]

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
