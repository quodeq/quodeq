from __future__ import annotations


def is_repo_url(repo_input: str) -> bool:
    """Return True if the input looks like a remote repository URL."""
    return repo_input.startswith(("http://", "https://", "git@"))
