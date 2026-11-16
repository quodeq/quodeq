"""Content-derived identity for dismissed findings.

A dismissal used to be keyed on ``(req, file, line)``. Any commit that shifted
the flagged code by a line made the key stop matching: the finding came back
on the next run as if it had never been reviewed and the actions-log entry
became dead weight (issue #1165). The identity is now ``(req, file,
fingerprint)`` where the fingerprint is the SARIF-stable
``sha256(req | whitespace-normalized snippet)`` the precedent matcher already
computes. The line is kept as a display hint and as the identity of findings
that carry no snippet (scope-level findings, file-level deterministic checks).

Key shapes, used wherever a "dismiss key" travels as a bare tuple (run key
sets, detail lookups): ``(req, file, line: int)`` for a line-keyed entry and
``(req, file, fingerprint: str)`` for a fingerprinted one. The type of the
third element tells them apart. The net state built from these keys and the
membership predicate live in ``core.dismissals``.
"""
from __future__ import annotations

import hashlib
import re
from typing import NamedTuple

_WS_RE = re.compile(r"\s+")
# A snippet the publisher did not share travels as this token, which carries
# the finding's fingerprint so dismissals and run diffs still match it on a
# shared clone. A finding without a req is fingerprinted under its own (empty)
# req only, so a dismissal recorded under its principle does not match there.
WITHHELD_SNIPPET_PREFIX = "quodeq:snippet-withheld:"
_WITHHELD_RE = re.compile(re.escape(WITHHELD_SNIPPET_PREFIX) + r"([0-9a-f]{64})")

DismissKey = tuple[str, str, object]
"""``(req, file, line)`` or ``(req, file, fingerprint)``; see the module doc."""


def normalize_snippet(snippet: str | None) -> str:
    """Collapse runs of whitespace and trim trailing punctuation/space."""
    if not snippet:
        return ""
    collapsed = _WS_RE.sub(" ", snippet).strip()
    return collapsed.rstrip(",;.")


def fingerprint(req: str | None, snippet: str | None) -> str | None:
    """Hex sha256 of ``req + '|' + normalized_snippet``, or None when blank.

    Frozen: ``ci/sarif.py`` writes it as ``partialFingerprints`` under the
    versioned key ``quodeqReqSnippet/v1``, and code-scanning hosts correlate
    alerts across uploads by it. Returning None for blank inputs lets callers
    skip lookup entirely instead of poisoning a set with an all-empty key.
    """
    withheld = _WITHHELD_RE.fullmatch(snippet.strip()) if snippet else None
    if withheld:
        return withheld.group(1)
    norm = normalize_snippet(snippet)
    req_part = (req or "").strip()
    if not req_part and not norm:
        return None
    payload = f"{req_part}|{norm}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def snippet_fingerprint(req: str | None, snippet: str | None) -> str | None:
    """The dismiss identity of a finding, or None when it has no snippet.

    Same hash as :func:`fingerprint`, but a blank snippet yields None instead
    of a req-only hash: every snippet-less finding under one requirement
    would otherwise share a fingerprint and one dismissal would hide them all.
    Those findings keep their line as identity.
    """
    if not normalize_snippet(snippet):
        return None
    return fingerprint(req, snippet)


def withheld_snippet(req: str | None, snippet: str | None) -> str:
    """The token that stands in for *snippet* when its code is not shared; "" for a blank one."""
    fp = snippet_fingerprint(req, snippet)
    return f"{WITHHELD_SNIPPET_PREFIX}{fp}" if fp else ""


def coerce_line(line: object) -> int:
    """Normalize a finding's line to the int the dismiss keys store.

    ``Finding.line`` is typed ``int | str | None`` and report renderers see
    whatever a report carried, so ``"12"`` must match a stored ``12`` and
    anything unusable keys on ``0``.
    """
    try:
        return int(line)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return 0


def dismiss_identities(req: str | None, principle: str | None) -> tuple[str, ...]:
    """Every requirement id a dismissal of this finding may be recorded under.

    The UI stores ``req || principle`` (``buildDismissPayload``); the
    assistant's draft/apply path records a no-req finding with an empty req.
    A finding with a req is only ever keyed on it.
    """
    ident = req or principle or ""
    if req:
        return (ident,)
    return (ident, "") if ident else ("",)


def finding_dismiss_keys(
    *, req: str | None, principle: str | None, file: str | None, line: object,
    snippet: str | None,
) -> set[DismissKey]:
    """Every dismiss key that would hide this finding (both shapes, all idents).

    Feeds the per-run key sets the score cache intersects with the project's
    dismissals, so a dismissal recorded under any accepted identity changes
    the versions of exactly the runs holding that finding.
    """
    file_key = file or ""
    line_key = coerce_line(line)
    keys: set[DismissKey] = set()
    for ident in dismiss_identities(req, principle):
        keys.add((ident, file_key, line_key))
        fp = snippet_fingerprint(ident, snippet)
        if fp is not None:
            keys.add((ident, file_key, fp))
    return keys


class SuppressionSubject(NamedTuple):
    """What the app's suppression predicate reads of one violation, its snippet reduced to fingerprints.

    ``fingerprints`` holds one :func:`snippet_fingerprint` per
    ``dismiss_identities(req, principle)`` identity, in that order, so a stored
    subject can be judged without its snippet. ``deleted_file`` is the file part
    of the violation's delete key: it differs from ``file`` only for a combined
    ``path:suffix`` spelling whose suffix is not a line number.
    """

    dimension: str
    req: str
    principle: str
    file: str
    line: int
    fingerprints: tuple[str | None, ...]
    deleted_file: str


def dismiss_fingerprints(
    req: str | None, principle: str | None, snippet: str | None,
) -> tuple[str | None, ...]:
    """The snippet fingerprint under each identity a dismissal of this finding may be recorded under."""
    return tuple(snippet_fingerprint(ident, snippet) for ident in dismiss_identities(req, principle))
