"""The Python and UI vocabulary gates must agree on every vocabulary both know.

tools/check_vocab_literals.py (VOCABULARIES) and the UI's
eslint.vocab.config.js (VOCABULARIES) are two hand-written word lists for
the same enums. A word added on one side only would leave the other gate
blind to it, and neither gate's own tests would notice. This reads the JS
object literal and compares it list for list; the UI name is the Python
name in camelCase.
"""
from __future__ import annotations

import re
from pathlib import Path

import check_vocab_literals

_UI_CONFIG = Path(__file__).resolve().parents[2] / "src" / "quodeq" / "ui" / "eslint.vocab.config.js"
# Gated in Python only: FileDoneStatus has no UI reader, and the UI's provider
# words would collide with the assistant-mode word "custom".
_PYTHON_ONLY = {"FileDoneStatus", "Provider"}


def _ui_vocabularies() -> dict[str, frozenset[str]]:
    text = _UI_CONFIG.read_text(encoding="utf-8")
    block = re.search(r"const VOCABULARIES = \{(.*?)\n\};", text, re.DOTALL)
    assert block, f"VOCABULARIES not found in {_UI_CONFIG}"
    lists = re.findall(r"(\w+):\s*\[(.*?)\]", block.group(1), re.DOTALL)
    return {name[0].upper() + name[1:]: frozenset(re.findall(r"'([^']*)'", words)) for name, words in lists}


def test_every_ui_word_list_matches_its_python_twin():
    python = check_vocab_literals.VOCABULARIES
    for name, words in _ui_vocabularies().items():
        assert name in python, f"UI gate vocabulary {name} has no Python twin"
        assert words == python[name], name


def test_the_ui_gate_knows_every_python_vocabulary_but_the_python_only_ones():
    assert set(check_vocab_literals.VOCABULARIES) - set(_ui_vocabularies()) == _PYTHON_ONLY
