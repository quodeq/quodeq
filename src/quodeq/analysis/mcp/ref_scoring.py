"""Reference scoring: pick the best compiled-standard refs for a finding.

Given a list of candidate refs and the finding's description/reason text,
selects one ref per source type (CWE, CISQ, etc.) using word-overlap scoring.
"""
from __future__ import annotations

_STOP_WORDS = frozenset({
    "a", "an", "the", "of", "to", "in", "for", "is", "and", "or", "not", "with", "without",
})


def text_overlap(ref_name: str, description: str, reason: str) -> int:
    """Score how well a ref name matches the finding text by counting shared words."""
    stop = _STOP_WORDS
    ref_words = set(ref_name.lower().split()) - stop
    finding_words = (set(description.lower().split()) | set(reason.lower().split())) - stop
    return len(ref_words & finding_words)


def select_best_refs(
    all_refs: list[dict], description: str, reason: str,
) -> list[dict]:
    """Pick one ref per source type (CWE, CISQ, etc.), choosing the best text match.

    When no words overlap at all, picks the broadest (first/lowest-ID) ref as a
    safe default rather than an arbitrary specific one.
    """
    by_source: dict[str, list[dict]] = {}
    for ref in all_refs:
        source = ref.get("source", "") or ref.get("label", "").split("-")[0]
        by_source.setdefault(source, []).append(ref)

    result: list[dict] = []
    for source, refs in by_source.items():
        if len(refs) == 1:
            result.append(refs[0])
        else:
            scored = [(r, text_overlap(r.get("name", ""), description, reason)) for r in refs]
            max_score = max(s for _, s in scored)
            if max_score == 0:
                # No text match -- pick the broadest (first listed, typically the parent)
                result.append(refs[0])
            else:
                result.append(max(scored, key=lambda x: x[1])[0])
    return result
