"""I/O-bound resolvers — turn on-disk eval files into ``DimResolution``s.

This module is currently a stub: ``resolve_latest_per_dim``,
``is_visible_in_history`` and ``is_eligible_for_chart_bar`` were removed on
2026-09-22 (the run-list-vocabulary-into-RunState migration) because nothing
in ``src`` called them — the eval-file-provenance resolver they implemented
was never wired into a live view. ``DimResolution`` (``_models.py``) is kept
for whichever follow-up PR picks this back up; see ``README.md`` for the
package's model.
"""
from __future__ import annotations

__all__: list[str] = []
