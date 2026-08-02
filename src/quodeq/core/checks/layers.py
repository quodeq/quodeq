"""Which files hold inner-layer code, by directory convention.

A checker can only judge a project whose layers it can name. We read that
from directory names because the alternative -- inferring layers from import
shape -- reports architecture violations at projects that never claimed to
have an architecture.

The consequence is deliberate: a project with no recognisable inner layer
produces NO findings. Not a pass, not a wall of violations. Silence is the
honest answer when the standard's subject cannot be located.
"""
from __future__ import annotations

from collections.abc import Iterable

# Directory names that conventionally hold enterprise/application logic --
# the layers Clean Architecture requires to stay free of outer concerns.
#
# ``models`` is deliberately absent: it names the ORM directory at least as
# often as the domain one, and a wrong guess here mislabels every finding
# built on top of it.
INNER_LAYER_DIRS = frozenset({
    "domain",
    "entities",
    "entity",
    "usecases",
    "use_cases",
    "use-cases",
    "interactors",
    "application",
    "core",
    "business",
})


def _segments(path: str) -> list[str]:
    """Path segments, tolerating Windows separators."""
    return [s for s in path.replace("\\", "/").split("/") if s]


def is_inner_layer_path(path: str) -> bool:
    """True when *path* sits under a conventional inner-layer directory.

    Matching is on whole path segments: ``core_utils/`` is not ``core/``.
    The final segment is the file name and never counts as a directory.
    """
    segments = _segments(path)
    if len(segments) < 2:
        return False
    return any(s.lower() in INNER_LAYER_DIRS for s in segments[:-1])


def inner_layer_files(paths: Iterable[str]) -> frozenset[str]:
    """The subset of *paths* that live in an inner layer (possibly empty)."""
    return frozenset(p for p in paths if is_inner_layer_path(p))
