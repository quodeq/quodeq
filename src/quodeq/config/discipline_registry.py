"""Discipline detection rules parsed from a .conf file.

Re-exports from internal modules to preserve the public API.
"""

from quodeq.config._discipline_rule import DisciplineRule  # noqa: F401
from quodeq.config._discipline_detection import DisciplineRegistry  # noqa: F401

__all__ = ["DisciplineRule", "DisciplineRegistry"]
