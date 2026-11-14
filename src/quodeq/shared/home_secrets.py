"""Where secrets usually sit under a user's home, for a sandbox that cannot
hide the whole home.

Seatbelt and bubblewrap make the home unreadable and read back only what a
run needs, so they need no such list. firejail's fallback leaves the home
readable and denies these by name instead: the credential stores of the
usual tools, the logins of the agent CLIs, the browsers' profiles, and
Quodeq's run dir, which holds the per-launch secret its local API accepts.
"""
from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from quodeq.shared.env_paths import run_dir_path

# Relative to the home. Only the ones that exist become sandbox rules.
HOME_SECRET_PATHS: tuple[str, ...] = (
    ".ssh", ".gnupg", ".aws", ".azure", ".config/gcloud", ".kube", ".docker",
    ".netrc", ".git-credentials", ".config/git/credentials", ".config/gh", ".config/hub",
    ".npmrc", ".pypirc", ".cargo/credentials", ".cargo/credentials.toml", ".gem/credentials",
    ".password-store", ".local/share/keyrings", ".vault-token", ".config/op",
    ".terraform.d/credentials.tfrc.json",
    ".claude", ".claude.json", ".codex", ".gemini", ".copilot", ".config/github-copilot",
    ".mozilla", ".config/google-chrome", ".config/chromium",
)


def home_secret_paths(granted: Iterable[str] = ()) -> list[str]:
    """The secret stores that exist under this user's home, and Quodeq's run
    dir, for a sandbox to deny reads of.

    A store that is, or holds, a path in *granted* is left out: the CLI being
    run keeps its own login (its home is writable, or one file of it is).
    """
    kept = [Path(g).resolve() for g in granted if g]
    candidates = [*(Path.home() / rel for rel in HOME_SECRET_PATHS), run_dir_path()]
    return [str(path) for path in dict.fromkeys(candidates)
            if os.path.lexists(path) and not any(g.is_relative_to(path.resolve()) for g in kept)]
