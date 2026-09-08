"""Read seams for previously-dismissed findings, consumed by precedent matching."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

DismissedSnippetsReader = Callable[[Path], Iterable[tuple[str | None, str | None]]]
"""Reads ``(requirement, snippet)`` pairs for every dismissed finding under a
run directory.

Mirrors the public surface of
``quodeq.data.sqlite.findings_queries.read_dismissed_snippets_strict``; consumers
type against this alias so a fake reader can stand in for isolated tests
without importing the sqlite layer.
"""

DismissedSourceStamp = Callable[[Path], object | None]
"""Cheap freshness stamp of the dismissed-findings source under a run directory.

None means the run has no source at all (nothing to read); any other value
must compare equal until the source is rewritten, and differ afterwards.
``load_precedent_fingerprints`` memoizes each run's fingerprints on this
stamp so a project whose history has settled re-reads nothing on later
scans. Production default:
``quodeq.data.sqlite.findings_queries.dismissed_source_stamp``.
"""
