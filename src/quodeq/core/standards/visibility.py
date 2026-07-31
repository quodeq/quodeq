"""Per-project selection of which standards are shown.

Hiding a standard is project configuration, not a per-browser view preference:
the dashboard and the assistant must both agree on which standards are in
play (there is no CLI consumer). The selection lives in the analyzed
repository at
``<project root>/.quodeq/standards-visibility.json``, alongside
``standards-overrides.json``, so the whole team shares it:

    {"version": 1, "visibleStandardIds": ["security", "reliability"]}

An absent file means the six ISO defaults, NOT "everything". Quodeq ships more
built-in standards than the default selection shows, so treating absence as
"no filtering" would leave a fresh install disagreeing with its own dashboard.

A malformed file never fails a read; it degrades to the defaults with a warning.\nRead/write of the file itself lives in ``data/fs/standards_prefs.py``.
"""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

VISIBILITY_RELPATH = Path(".quodeq") / "standards-visibility.json"

# Must stay in lockstep with DEFAULT_VISIBLE_STANDARDS in
# src/quodeq/ui/src/constants.js -- pinned by
# tests/core/test_visible_standards_defaults_match_ui.py.
DEFAULT_VISIBLE_STANDARDS: tuple[str, ...] = (
    "security", "reliability", "maintainability",
    "performance", "usability", "flexibility",
)


def normalize_ids(ids: Iterable[object]) -> tuple[str, ...]:
    """Lowercase, de-duplicate and drop non-strings, preserving first order."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in ids:
        if not isinstance(raw, str):
            continue
        key = raw.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return tuple(out)


def validate_visible_ids(raw: object, known_ids: set[str]) -> tuple[list[str], list[str]]:
    """Validate a proposed selection; returns ``(clean, errors)``.

    ``clean`` is empty whenever ``errors`` is non-empty: API writes are
    all-or-nothing, unlike load-time parsing which skips bad entries.
    """
    if not isinstance(raw, list):
        return [], ["visibleStandardIds must be an array"]
    errors: list[str] = []
    for entry in raw:
        if not isinstance(entry, str):
            errors.append(f"{entry!r}: must be a string")
        elif entry.strip().lower() not in known_ids:
            errors.append(f"{entry}: unknown standard")
    if errors:
        return [], errors
    return list(normalize_ids(raw)), []


def partition_visible(
    ids: Iterable[str], visible: tuple[str, ...] | None,
) -> tuple[list[str], list[str]]:
    """Split ``ids`` into ``(visible, hidden)`` against a selection.

    ``visible=None`` means no filtering is configured for this session, so
    everything is visible and nothing is reported hidden. Comparison is on the
    lowercase id, matching the UI's ``visibleSet.has(d.dimension.toLowerCase())``;
    the returned strings keep their original casing.
    """
    if visible is None:
        return list(ids), []
    allowed = set(visible)
    shown: list[str] = []
    hidden: list[str] = []
    for value in ids:
        (shown if (value or "").strip().lower() in allowed else hidden).append(value)
    return shown, hidden


def hidden_ids_for_names(
    names: Iterable[str], visible: tuple[str, ...] | None,
) -> list[str]:
    """Which of *names* are hidden, de-duplicated and sorted.

    A blank/missing name is always treated as visible -- there is no
    dimension to hide -- and must never itself surface as a hidden id.
    Shared by every read surface (assistant tools and the overview) so
    "what counts as hidden" cannot drift between them.
    """
    non_blank = [n for n in names if (n or "").strip()]
    _, hidden = partition_visible(non_blank, visible)
    return sorted({h.strip().lower() for h in hidden})


def partition_entries_visible(
    entries: list[dict], visible: tuple[str, ...] | None, key: str = "dimension",
) -> tuple[list[dict], list[str]]:
    """Drop entries whose ``entry[key]`` the selection hides.

    Returns ``(kept, hidden_ids)``. ``hidden_ids`` is de-duplicated and sorted
    so the payload is stable, and is what lets a caller offer the withheld
    data instead of silently omitting it. An entry with a blank/missing key is
    always kept -- there is nothing to hide it as.
    """
    names = [str(e.get(key) or "") for e in entries]
    hidden = hidden_ids_for_names(names, visible)
    if not hidden:
        return entries, []
    hidden_set = set(hidden)
    kept = [e for e, n in zip(entries, names, strict=True)
            if not n.strip() or n.strip().lower() not in hidden_set]
    return kept, hidden
