"""Model-id normalization shared by assistant and analysis CLI builders."""
from __future__ import annotations

import re

# Bare version shorthand like "5.4" or "5.3-codex" (no vendor prefix).
_NUMERIC_SHORTHAND = re.compile(r"\d+(?:\.\d+)*(?:-[A-Za-z0-9_.-]+)?")

# NOTE: compares against the literal "codex", not Provider.CODEX -- shared/
# is a strict layer (tools/check_imports.py) that may import only core/, and
# Provider lives in config/. "codex" is dropped from VOCAB_WORDS in
# tools/check_vocab_literals.py for this reason (see that file's comment).


def normalize_model_id(cmd: str, model: str) -> str:
    """Expand provider-specific model shorthand (codex: "5.4" -> "gpt-5.4")."""
    value = model.strip()
    if cmd == "codex" and _NUMERIC_SHORTHAND.fullmatch(value):
        return f"gpt-{value}"
    return value
