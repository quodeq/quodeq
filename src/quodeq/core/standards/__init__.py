"""Standards reference extraction utilities (pure).

Loading standards from disk lives in ``data/fs/standards_loader.py``: the
core layer holds only the parsing/extraction logic.
"""

from quodeq.core.standards.refs import (
    extract_refs,
    extract_requirements,
    ref_label,
)

__all__ = [
    "extract_refs",
    "extract_requirements",
    "ref_label",
]
