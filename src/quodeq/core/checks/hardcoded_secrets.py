"""Credentials hardcoded in source -- S-CON-1.

The model never sees these values: the prompt carries a typed placeholder
instead (see ``core.secret_scan``). So the finding is made here, locally and
deterministically, at the exact line, with the value already masked in the
snippet that gets stored.

Violations only. A clean scan emits nothing rather than a compliance row: the
model still judges S-CON-1 for everything a pattern cannot see (credentials
built from parts, weak defaults), and a compliance row per project would
claim more than a pattern scan has earned.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Iterable

from quodeq.core.checks._judgments import violation
from quodeq.core.checks.model import SourceLocation
from quodeq.core.events.models import Judgment
from quodeq.core.secret_scan import find_secrets, redact
from quodeq.core.types.severity import Severity

REQ = "S-CON-1"
VIOLATION_TYPE = "hardcoded-secret"


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
            judgment = violation(
                req=REQ, dimension=dimension, at=SourceLocation(file, hit.line),
                title=f"Hardcoded {_label(hit.kind)}",
                reason=(
                    f"A {_label(hit.kind)} is written into the source. Anyone "
                    f"who can read the repository can use it, and rotating it "
                    f"means a code change. Load it from the environment or a "
                    f"secret store instead."
                ),
            )
            out.append(dataclasses.replace(
                judgment, severity=Severity.CRITICAL, snippet=snippet.strip(),
                violation_type=VIOLATION_TYPE,
            ))
    return out
