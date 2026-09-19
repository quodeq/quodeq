"""Precedent downweight: exact-fingerprint and semantic-similarity tiers.

Split out of enricher.py to keep it under the file-size ratchet. Semantic
similarity is consulted only on an exact-tier miss (see
``apply_precedent_downweight``). The batch path -- ``precedent_scores``,
called from ``FindingEnricher.precedent_scores`` -- computes every eligible
finding's score with one ``PrecedentCorpus.match_many`` call instead of one
``match`` call per finding (finding 5598).
"""
from __future__ import annotations

from typing import Callable

from quodeq.context.precedent import (
    PrecedentCorpus,
    fingerprint as _precedent_fingerprint,
    precedent_text as _precedent_text,
)
from quodeq.core._constants import FULL_CONFIDENCE
from quodeq.core.observability import NULL_LOG, LogSink

_PRECEDENT_DOWNWEIGHT = 25

# Sentinel distinguishing "the caller didn't supply a score" from an
# explicit `None` (a batch score that came back empty).
UNSET_SCORE: float | None = object()  # type: ignore[assignment]
# Deprecated private spelling, kept one release for existing importers.
_UNSET = UNSET_SCORE


def _semantic_eligible(finding: dict[str, object]) -> bool:
    """Scope-level and empty-snippet findings are excluded from the semantic
    tier: their enriched snippet is the first ~40 lines of the file regardless
    of the issue (enrichment.py), so any two scope-level findings on the same
    file embed near-identical texts and would cross-match across requirements.
    The exact tier still covers them."""
    line = finding.get("line")
    if not isinstance(line, int) or line <= 0:
        return False
    if finding.get("scope"):
        return False
    snippet = finding.get("snippet")
    return isinstance(snippet, str) and bool(snippet.strip())


def _precedent_probe(
    finding: dict[str, object], fingerprints: set[str] | None,
) -> tuple[bool, str | None]:
    """``(exact_matched, text_to_embed)`` for one finding.

    Single source of both tiers' inputs, so the fingerprint is computed once
    per finding for the downweight and the batch scorer alike. The text is
    None when the semantic lookup is skipped: not a violation, already
    exact-fingerprint matched, or ineligible (see `_semantic_eligible`).
    """
    if finding.get("t") != "violation":
        return False, None
    req = finding.get("req")
    snippet = finding.get("snippet")
    req_s = req if isinstance(req, str) else None
    snippet_s = snippet if isinstance(snippet, str) else None
    fp = _precedent_fingerprint(req_s, snippet_s)
    if fp is not None and fingerprints is not None and fp in fingerprints:
        return True, None
    if not _semantic_eligible(finding):
        return False, None
    return False, _precedent_text(req_s, snippet_s)


def apply_precedent_downweight(
    finding: dict[str, object],
    fingerprints: set[str] | None,
    corpus: PrecedentCorpus | None = None,
    *, score: float | None = UNSET_SCORE, log: LogSink = NULL_LOG,
) -> str | None:
    """Drop confidence to ~25 when this finding matches a prior dismissal.

    Tier 1: exact fingerprint (unchanged, SARIF-compatible). Tier 2: semantic
    similarity via the corpus, only on exact miss and only for eligible
    findings. *score* lets a caller that already ran the batch lookup
    (``precedent_scores``) skip a second ``corpus.match`` call.

    Returns the tier that matched, ``"exact"`` or ``"semantic"``, or None.
    Only the exact tier is certain enough to act on beyond the confidence
    field (see ``FindingEnricher._after_precedent``).
    """
    matched, text = _precedent_probe(finding, fingerprints)
    tier: str | None = "exact" if matched else None

    if not matched and corpus is not None and text is not None:
        if score is UNSET_SCORE:
            score = corpus.match(text)
        if score is not None and score >= corpus.threshold:
            matched = True
            tier = "semantic"
            log.debug(
                f"Semantic precedent match ({score:.3f}) for "
                f"{finding.get('file')}:{finding.get('line')}"
            )

    if not matched:
        return None
    existing = finding.get("confidence")
    if existing is None or existing == FULL_CONFIDENCE:
        finding["confidence"] = _PRECEDENT_DOWNWEIGHT
    return tier


# Deprecated private spelling, kept one release for existing importers.
_apply_precedent_downweight = apply_precedent_downweight


def precedent_scores(
    corpus: PrecedentCorpus | None,
    fingerprints: set[str] | None,
    findings: list[dict],
) -> list[float | None]:
    """Best-effort semantic precedent score per finding, one embed call.

    None for a finding that skips the lookup (`_precedent_probe`), and for
    every finding when *corpus* is None.
    """
    if corpus is None:
        return [None] * len(findings)
    texts = [_precedent_probe(f, fingerprints)[1] for f in findings]
    pending = [t for t in texts if t is not None]
    if not pending:
        return [None] * len(findings)
    scores = iter(corpus.match_many(pending))
    return [None if t is None else next(scores) for t in texts]


def notify_precedent_match(
    hook: Callable[[dict], None] | None, finding: dict, *, log: LogSink = NULL_LOG,
) -> None:
    """Hand an exact precedent match to *hook*.

    The hook appends to the project action log, outside the run. A file it
    cannot open or lock (OSError), or an event it cannot serialize
    (TypeError, ValueError), is logged and costs nothing: the finding itself
    is already enriched and still written. Anything else is a bug and
    propagates.
    """
    if hook is None:
        return
    try:
        hook(finding)
    except (OSError, TypeError, ValueError) as exc:
        log.warning(f"Precedent hook failed for {finding.get('file')}:{finding.get('line')}: {exc}")
