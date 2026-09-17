"""Precedent downweight: exact-fingerprint and semantic-similarity tiers.

Split out of enricher.py to keep it under the file-size ratchet. Semantic
similarity is consulted only on an exact-tier miss (see
``_apply_precedent_downweight``). The batch path -- ``precedent_scores``,
called from ``FindingEnricher.precedent_scores`` -- computes every eligible
finding's score with one ``PrecedentCorpus.match_many`` call instead of one
``match`` call per finding (finding 5598).
"""
from __future__ import annotations

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
_UNSET: float | None = object()  # type: ignore[assignment]


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


def _precedent_lookup_text(
    finding: dict[str, object], fingerprints: set[str] | None,
) -> str | None:
    """Text to embed for the semantic tier, or None to skip the lookup: not
    a violation, already exact-fingerprint matched, or ineligible (see
    `_semantic_eligible`)."""
    if finding.get("t") != "violation":
        return None
    req = finding.get("req")
    snippet = finding.get("snippet")
    req_s = req if isinstance(req, str) else None
    snippet_s = snippet if isinstance(snippet, str) else None
    fp = _precedent_fingerprint(req_s, snippet_s)
    if fp is not None and fingerprints is not None and fp in fingerprints:
        return None
    if not _semantic_eligible(finding):
        return None
    return _precedent_text(req_s, snippet_s)


def _apply_precedent_downweight(
    finding: dict[str, object],
    fingerprints: set[str] | None,
    corpus: PrecedentCorpus | None = None,
    *, score: float | None = _UNSET, log: LogSink = NULL_LOG,
) -> None:
    """Drop confidence to ~25 when this finding matches a prior dismissal.

    Tier 1: exact fingerprint (unchanged, SARIF-compatible). Tier 2: semantic
    similarity via the corpus, only on exact miss and only for eligible
    findings. *score* lets a caller that already ran the batch lookup
    (``precedent_scores``) skip a second ``corpus.match`` call.
    """
    if finding.get("t") != "violation":
        return
    req = finding.get("req")
    snippet = finding.get("snippet")
    fp = _precedent_fingerprint(
        req if isinstance(req, str) else None,
        snippet if isinstance(snippet, str) else None,
    )
    matched = fp is not None and fingerprints is not None and fp in fingerprints

    if not matched and corpus is not None:
        text = _precedent_lookup_text(finding, fingerprints)
        if text is not None:
            if score is _UNSET:
                score = corpus.match(text)
            if score is not None and score >= corpus.threshold:
                matched = True
                log.debug(
                    f"Semantic precedent match ({score:.3f}) for "
                    f"{finding.get('file')}:{finding.get('line')}"
                )

    if not matched:
        return
    existing = finding.get("confidence")
    if existing is None or existing == FULL_CONFIDENCE:
        finding["confidence"] = _PRECEDENT_DOWNWEIGHT


def precedent_scores(
    corpus: PrecedentCorpus | None,
    fingerprints: set[str] | None,
    findings: list[dict],
) -> list[float | None]:
    """Best-effort semantic precedent score per finding, one embed call.

    None for a finding that skips the lookup (`_precedent_lookup_text`), and
    for every finding when *corpus* is None.
    """
    if corpus is None:
        return [None] * len(findings)
    texts = [_precedent_lookup_text(f, fingerprints) for f in findings]
    pending = [t for t in texts if t is not None]
    if not pending:
        return [None] * len(findings)
    scores = iter(corpus.match_many(pending))
    return [None if t is None else next(scores) for t in texts]
