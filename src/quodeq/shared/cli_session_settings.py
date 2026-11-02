"""Session-only permission settings for an agent CLI that takes them as JSON.

Antigravity's CLI (agy) reads ``--settings '<json>'`` for one run without
saving it. Quodeq passes its own permission rules that way: an allow list
naming exactly what the run may do (the Quodeq MCP server's tools, reads of
the analysed repo) and a deny list for everything a prompt-injected repo
could use to act (shell commands, writes, URLs, the browser). In headless
mode agy never prompts: a denied call fails back to the model, and a call
neither list names is refused and ends the turn.

The provider catalog holds the rules (``session_settings`` in
ai_providers.json); ``{repo}`` in a rule stands for the analysed repo.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_PLACEHOLDER = "{repo}"
_FLAG_DEFAULT = "--settings"


def _fill(value: object, repo: str) -> object:
    if isinstance(value, str):
        return value.replace(REPO_PLACEHOLDER, repo)
    if isinstance(value, list):
        return [_fill(v, repo) for v in value]
    if isinstance(value, dict):
        return {k: _fill(v, repo) for k, v in value.items()}
    return value


def session_settings_args(spec: dict | None, repo: Path | None = None) -> list[str]:
    """``[flag, json]`` for a ``session_settings`` catalog block, or ``[]``.

    *spec* is ``{"flag": ..., "settings": {...}}``. A rule naming ``{repo}``
    needs *repo*; without one the block is not emitted at all, so a run never
    starts with a rule that grants a literal ``{repo}`` path.
    """
    if not spec or "settings" not in spec:
        return []
    settings = spec["settings"]
    if REPO_PLACEHOLDER in json.dumps(settings):
        if repo is None:
            return []
        settings = _fill(settings, str(repo.resolve()))
    return [spec.get("flag", _FLAG_DEFAULT), json.dumps(settings, separators=(",", ":"))]
