"""Bucketing — group runs into chart-friendly time windows.

This module is currently a stub: ``bucket_runs_by_day`` and
``pick_representative_run`` were removed on 2026-09-22 (the
run-list-vocabulary-into-RunState migration) because nothing in ``src``
called them — the score-history chart never started consuming this
package (see the parent README's migration note). ``BucketView``
(``_models.py``) is kept for whichever follow-up PR picks this back up.
"""
from __future__ import annotations

__all__: list[str] = []
