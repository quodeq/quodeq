"""Deterministic secret detection and typed-placeholder redaction.

Source code is sent to a model and its lines are stored in evaluation
artifacts (findings DB, evidence JSONL, reports, SARIF). A credential in the
code must reach neither. Deleting it would blind the hardcoded-secret
requirement, so each value is swapped for a typed placeholder
(``<REDACTED:aws_access_key>``): the model can still see a key is hardcoded
and where it flows, and the exact location is reported locally, without any
model, by the ``hardcoded-secrets`` checker.

Redaction never changes the line count, so line numbers in the prompt, in
findings and in stored context windows keep matching the file on disk.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

PLACEHOLDER_PREFIX = "<REDACTED:"

# The first rule to claim a span wins, so the specific token formats come
# before the generic keyword rule (and sk-ant- before the plain sk- one).
_TOKEN_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private_key", re.compile(
        r"-----BEGIN[A-Z ]*PRIVATE KEY(?: BLOCK)?-----"
        r"(?:.*?-----END[A-Z ]*PRIVATE KEY(?: BLOCK)?-----|.*\Z)",
        re.DOTALL)),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA|ABIA|ACCA)[A-Z0-9]{16}\b")),
    ("github_token", re.compile(
        r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})\b")),
    ("anthropic_api_key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    # Real keys always carry digits; the lookahead keeps kebab-case words
    # that happen to start with "sk-" out.
    ("openai_api_key", re.compile(
        r"\bsk-(?:proj-|svcacct-|admin-)?(?=[A-Za-z_\-]*\d)[A-Za-z0-9_\-]{20,}")),
    ("stripe_secret_key", re.compile(r"\b[rs]k_live_[A-Za-z0-9]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[abposr]-[A-Za-z0-9\-]{10,}")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("gitlab_token", re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}")),
    ("npm_token", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b")),
    ("jwt", re.compile(
        r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
)

# A quoted literal assigned to a credential-looking name:
#   password = "..."   "apiKey": "..."   SECRET_TOKEN := '...'
_KEYWORD_ASSIGNMENT = re.compile(
    r"""(?ix)
    (?:passw(?:or)?d|pwd|secret|token|api[_\-]?key|access[_\-]?key
       |private[_\-]?key|credential|auth[_\-]?key)
    [a-z0-9_.\-]*["']?
    \s*(?::=|=>|=|:)\s*
    (?P<q>["'`])(?P<value>[^"'`\s]{16,})(?P=q)
    """
)
_VALUE = "value"  # the _KEYWORD_ASSIGNMENT group holding the secret
_MIN_GENERIC_ENTROPY = 3.5
# Template and interpolation syntax: a reference to a secret, not one.
_INDIRECTION_MARKERS = ("${", "{{", "%(", "<", "process.env", "os.environ")


@dataclass(frozen=True, slots=True)
class SecretHit:
    """One detected secret: its 1-indexed *line*, the absolute character
    span ``[start, end)`` of the value in the scanned text, and its *kind*."""

    line: int
    start: int
    end: int
    kind: str


def placeholder(kind: str) -> str:
    """The typed stand-in sent and stored instead of a secret of *kind*."""
    return f"{PLACEHOLDER_PREFIX}{kind}>"


def _entropy(value: str) -> float:
    n = len(value)
    return -sum(c / n * math.log2(c / n) for c in Counter(value).values())


def _is_generic_secret(value: str) -> bool:
    if any(marker in value for marker in _INDIRECTION_MARKERS):
        return False
    return _entropy(value) >= _MIN_GENERIC_ENTROPY


def find_secrets(text: str) -> list[SecretHit]:
    """Every secret in *text*, in order of position, without overlaps."""
    found: list[tuple[int, int, str]] = []

    def claim(start: int, end: int, kind: str) -> None:
        if not any(start < e and s < end for s, e, _ in found):
            found.append((start, end, kind))

    for kind, pattern in _TOKEN_RULES:
        for m in pattern.finditer(text):
            claim(m.start(), m.end(), kind)
    for m in _KEYWORD_ASSIGNMENT.finditer(text):
        if _is_generic_secret(m.group(_VALUE)):
            claim(m.start(_VALUE), m.end(_VALUE), "generic_secret")

    found.sort()
    return [
        SecretHit(line=text.count("\n", 0, start) + 1, start=start, end=end, kind=kind)
        for start, end, kind in found
    ]


def redact(text: str) -> str:
    """*text* with every secret replaced by its typed placeholder.

    A multi-line secret (a PEM block) keeps its newlines after the
    placeholder, so every later line stays at the same line number.
    """
    if not text:
        return text
    hits = find_secrets(text)
    if not hits:
        return text
    out: list[str] = []
    cursor = 0
    for hit in hits:
        out.append(text[cursor:hit.start])
        out.append(placeholder(hit.kind) + "\n" * text.count("\n", hit.start, hit.end))
        cursor = hit.end
    out.append(text[cursor:])
    return "".join(out)
