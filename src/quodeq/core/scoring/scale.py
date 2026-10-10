"""The project-scale and formula inputs one principle's grade is computed with.

Shared by the CLI engine (``core/scoring/principle.py``) and the SQL
projector (``core/scoring/projector_scoring.py``) so both paths take the
same object and cannot drift on which inputs reach the formula.
"""
from __future__ import annotations

from dataclasses import dataclass

from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams


@dataclass(frozen=True)
class PrincipleGradeScale:
    """Confidence-scaling and formula inputs for one principle's grade.

    ``source_file_count``/``scale_multiplier`` feed
    ``classify_confidence_level`` (thin evidence relative to project size) and
    the requirement spread; ``params`` is the scoring formula. Defaults
    reproduce the pre-object call shape (no scaling, default formula).
    """

    source_file_count: int = 0
    scale_multiplier: int = 1
    params: ScoringParams = DEFAULT_PARAMS
