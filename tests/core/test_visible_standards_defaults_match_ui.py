"""The visible-standards default is declared in two languages. Pin them.

Backend filtering (quodeq.core.standards.visibility) and the dashboard's
pre-hydration fallback (ui/src/constants.js) must agree, or the assistant and
the Overview disagree on a fresh install -- the exact bug this file guards.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from quodeq.core.standards.visibility import DEFAULT_VISIBLE_STANDARDS

_CONSTANTS = (Path(__file__).resolve().parents[2]
              / "src" / "quodeq" / "ui" / "src" / "constants.js")
_PATTERN = re.compile(
    r"export const DEFAULT_VISIBLE_STANDARDS\s*=\s*\[(.*?)\]", re.DOTALL)


def _ui_defaults() -> tuple[str, ...]:
    match = _PATTERN.search(_CONSTANTS.read_text(encoding="utf-8"))
    assert match, f"DEFAULT_VISIBLE_STANDARDS not found in {_CONSTANTS}"
    return tuple(json.loads(f"[{match.group(1).replace(chr(39), chr(34)).rstrip().rstrip(chr(44))}]"))


def test_python_defaults_match_the_ui_constant():
    assert DEFAULT_VISIBLE_STANDARDS == _ui_defaults()
