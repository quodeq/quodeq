"""Credentials hardcoded in source -- S-CON-1.

The model never sees these values: the prompt carries a typed placeholder
instead (see ``core.secret_scan``). So the finding is made here, locally and
deterministically, at the exact line, with the value already masked in the
snippet that gets stored.

Violations only. A clean scan emits nothing rather than a compliance row: the
model still judges S-CON-1 for everything a pattern cannot see (credentials
built from parts, weak defaults), and a compliance row per project would
claim more than a pattern scan has earned.

Credential files committed to the repository get the same treatment. The
agent CLIs are not allowed to read them (see ``core.secret_files``), so the
model can no longer notice one; they are reported here from what git tracks.
A ``.env`` kept out of git is where credentials belong and is not a finding.
A file counts only when it holds something: an ``.env`` with a
credential-named key set to a value, a ``.pem`` with a private key (not just
a certificate), or any non-empty key store or credential file.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

from quodeq.core.checks._judgments import critical, violation
from quodeq.core.checks.model import SourceLocation
from quodeq.core.events.models import Judgment
from quodeq.core.secret_files import KIND_ASSIGNMENTS, KIND_PRIVATE_KEY
from quodeq.core.secret_scan import PRIVATE_KEY, entropy, find_secrets, placeholder, redact

REQ = "S-CON-1"
VIOLATION_TYPE = "hardcoded-secret"
COMMITTED_FILE_VIOLATION_TYPE = "committed-secret-file"


def _label(kind: str) -> str:
    return kind.replace("_", " ")


def check_hardcoded_secrets(
    sources: Iterable[tuple[str, str]], *, dimension: str,
) -> list[Judgment]:
    """One violation per secret found in *sources* (``(file, text)`` pairs)."""
    out: list[Judgment] = []
    for file, text in sources:
        hits = find_secrets(text)
        if not hits:
            continue
        masked_lines = redact(text).split("\n")
        for hit in hits:
            snippet = masked_lines[hit.line - 1] if hit.line <= len(masked_lines) else ""
            out.append(critical(violation(
                req=REQ, dimension=dimension, at=SourceLocation(file, hit.line),
                title=f"Hardcoded {_label(hit.kind)}",
                reason=(
                    f"A {_label(hit.kind)} is written into the source. Anyone "
                    f"who can read the repository can use it, and rotating it "
                    f"means a code change. Load it from the environment or a "
                    f"secret store instead."
                ),
            ), snippet=snippet.strip(), violation_type=VIOLATION_TYPE))
    return out


# KEY=value, KEY: value, export KEY=value, npm's //host/:_authToken=value.
_ASSIGNMENT = re.compile(
    r"""(?imx)
    ^[ \t]*(?:export[ \t]+)?
    (?P<key>[\w.\-:/]*?
       (?:passw(?:or)?d|pwd|secret|token|api[_\-]?key|access[_\-]?key
          |private[_\-]?key|credential|auth)
       [\w.\-]*)
    [ \t]*[=:][ \t]*["']?
    (?P<value>[^\s"'#]{8,})
    """
)
_INDIRECTION_MARKERS = ("${", "{{", "%(", "<", "$(")
_MIN_ENTROPY = 3.0  # below this a value reads as a placeholder (changeme, xxxxxxxx)


def _assignment_hit(text: str) -> tuple[int, str] | None:
    """(line, masked line) of the first credential set to a real value."""
    for m in _ASSIGNMENT.finditer(text):
        value = m.group("value")
        if any(marker in value for marker in _INDIRECTION_MARKERS):
            continue
        if entropy(value) < _MIN_ENTROPY:
            continue
        line = text.count("\n", 0, m.start("key")) + 1
        return line, f"{m.group('key')}={placeholder('secret')}"
    return None


def _first_hit(kind: str, text: str) -> tuple[int, str] | None:
    """Where *text* (a file of *kind*) holds a credential, or None when it
    holds none."""
    tokens = find_secrets(text)
    if kind == KIND_PRIVATE_KEY:
        key = next((h for h in tokens if h.kind == PRIVATE_KEY), None)
        return (key.line, placeholder(key.kind)) if key else None
    if tokens:
        return tokens[0].line, placeholder(tokens[0].kind)
    if kind == KIND_ASSIGNMENTS:
        return _assignment_hit(text)
    return (1, "") if text.strip() else None


def check_committed_secret_files(
    files: Iterable[tuple[str, str, str]], *, dimension: str,
) -> list[Judgment]:
    """One violation per committed credential file in *files*
    (``(file, kind, text)`` triples)."""
    out: list[Judgment] = []
    for file, kind, text in files:
        hit = _first_hit(kind, text)
        if hit is None:
            continue
        line, snippet = hit
        out.append(critical(violation(
            req=REQ, dimension=dimension, at=SourceLocation(file, line),
            title="Credential file committed to the repository",
            reason=(
                "This file holds credentials and is tracked by git, so everyone "
                "with access to the repository or its history has them. Remove it "
                "from git, add it to .gitignore and rotate what it contained; "
                "removing it in a new commit leaves it in the history."
            ),
        ), snippet=snippet, violation_type=COMMITTED_FILE_VIOLATION_TYPE))
    return out
