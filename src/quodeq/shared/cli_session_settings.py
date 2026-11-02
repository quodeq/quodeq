"""Session-only permission settings for an agent CLI that takes them as JSON.

Antigravity's CLI (agy) reads ``--settings '<json>'`` for one run without
saving it. Quodeq passes its own permission rules that way: an allow list
naming exactly what the run may do (the Quodeq MCP server's tools, reads of
the analysed repo and of the outputs agy saved itself) and a deny list for
everything a prompt-injected repo could use to act (shell commands, writes,
URLs, the browser). In headless mode agy never prompts: a denied call fails
back to the model, and a call neither list names is refused and ends the turn.

The provider catalog holds the rules (``session_settings`` in
ai_providers.json). A ``{name}`` in a rule stands for a path the caller
supplies: ``{repo}`` the analysed repo, ``{agy_brain}`` where agy saves
oversized tool outputs (see ``shared/agy_home.py``).
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path

_FLAG_DEFAULT = "--settings"
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _fill(value: object, paths: Mapping[str, str]) -> object:
    if isinstance(value, str):
        return _PLACEHOLDER.sub(lambda m: paths[m[1]], value)
    if isinstance(value, list):
        return [_fill(v, paths) for v in value]
    if isinstance(value, dict):
        return {k: _fill(v, paths) for k, v in value.items()}
    return value


def session_settings_args(spec: dict | None, paths: Mapping[str, Path | None] | None = None) -> list[str]:
    """``[flag, json]`` for a ``session_settings`` catalog block, or ``[]``.

    *spec* is ``{"flag": ..., "settings": {...}}``. A rule naming a path the
    caller did not supply drops the whole block, so a run never starts with
    a rule that grants a literal ``{repo}`` path.
    """
    if not spec or "settings" not in spec:
        return []
    resolved = {k: str(p.resolve()) for k, p in (paths or {}).items() if p is not None}
    settings = spec["settings"]
    if any(name not in resolved for name in _PLACEHOLDER.findall(json.dumps(settings))):
        return []
    return [spec.get("flag", _FLAG_DEFAULT), json.dumps(_fill(settings, resolved), separators=(",", ":"))]
