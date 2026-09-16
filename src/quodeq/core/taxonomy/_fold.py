"""String folding for violation-type tags.

Table-driven and deliberately short: the taxonomy grows through aliases in
the standards JSON, never by widening these tables. Both sides of every
comparison (the model's tag, the declared codes, the declared aliases) are
folded the same way, so the folded form is a comparison key, not a label.
"""
from __future__ import annotations

import re

_SEPARATORS = re.compile(r"[\s_.]+")
_DASHES = re.compile(r"-{2,}")
_SYNONYMS: dict[str, str] = {
    "excess": "excessive",
    "error": "exception",
    "swallowed": "swallow",
    "swallowing": "swallow",
    "caught": "catch",
}
_STOPWORDS = frozenset({"a", "an", "of", "in", "the"})
_MIN_PLURAL_LEN = 4


def fold(raw: object) -> str:
    """Step 1: lowercase, unify separators to '-', collapse and trim dashes.

    Anything that is not a string, or folds to nothing, becomes ''.
    """
    if not isinstance(raw, str):
        return ""
    text = _SEPARATORS.sub("-", raw.strip().lower())
    return _DASHES.sub("-", text).strip("-")


def _fold_token(token: str) -> str:
    if token in _SYNONYMS:
        return _SYNONYMS[token]
    plural = len(token) >= _MIN_PLURAL_LEN and token.endswith("s") and not token.endswith("ss")
    if plural:
        singular = token[:-1]
        return _SYNONYMS.get(singular, singular)
    return token


def fold_tokens(folded: str) -> str:
    """Step 4: per-token synonym map, stopword drop, plural strip."""
    tokens = [_fold_token(t) for t in folded.split("-") if t and t not in _STOPWORDS]
    return "-".join(tokens)
