"""Classify current-vs-baseline PR violations as NEW or EXISTING."""
from __future__ import annotations


def _normalize_snippet(snippet: str) -> str:
    """Normalize whitespace for robust snippet comparison."""
    return " ".join((snippet or "").split())


def classify_violations(
    current: list[dict],
    baseline: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Classify each current violation as NEW or EXISTING based on baseline.

    A violation is EXISTING if the baseline has a violation in the same file
    with a matching (whitespace-normalized) snippet. Otherwise NEW.

    Returns (new_violations, existing_violations).
    """
    # Index baseline by file → set of normalized snippets
    baseline_index: dict[str, set[str]] = {}
    for v in baseline:
        file = v.get("file", "")
        snippet = _normalize_snippet(v.get("snippet", ""))
        if file:
            baseline_index.setdefault(file, set()).add(snippet)

    new_list: list[dict] = []
    existing_list: list[dict] = []
    for v in current:
        file = v.get("file", "")
        snippet = _normalize_snippet(v.get("snippet", ""))
        if snippet and snippet in baseline_index.get(file, set()):
            existing_list.append(v)
        else:
            new_list.append(v)
    return new_list, existing_list
