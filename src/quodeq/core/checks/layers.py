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


# The innermost of the inner layers. CLEA-DEP-02 is specifically about
# entities, not about every inner layer: a use case reaching an adapter is a
# different requirement (the inward rule), and conflating them would report one
# finding under the other's ID.
#
# ``core`` is here because it is the near-universal name for a package holding
# domain types when a project does not literally say "entities".
ENTITY_LAYER_DIRS = frozenset({"domain", "entities", "entity", "core"})

# Directory names that conventionally hold delivery, infrastructure and
# persistence concerns -- what entities must not depend on.
#
# Kept to names that are unambiguous in context. ``data`` and ``models`` are
# deliberately absent: both name a domain directory about as often as an
# adapter one, and a wrong guess here fabricates layering violations.
OUTER_LAYER_DIRS = frozenset({
    "adapters",
    "adapter",
    "infrastructure",
    "infra",
    "frameworks",
    "framework",
    "controllers",
    "presenters",
    "gateways",
    "repositories",
    "persistence",
    "drivers",
    "external",
    "api",
    "web",
    "ui",
    "views",
    "rest",
    "http",
    "database",
})


def _segments(path: str) -> list[str]:
    """Path segments, tolerating Windows separators."""
    return [s for s in path.replace("\\", "/").split("/") if s]


def is_entity_layer_path(path: str) -> bool:
    """True when *path* sits under a conventional entity/domain directory."""
    segments = _segments(path)
    if len(segments) < 2:
        return False
    return any(s.lower() in ENTITY_LAYER_DIRS for s in segments[:-1])


def is_outer_layer_module(module: str) -> bool:
    """True when a dotted module name passes through an outer-layer package.

    Judged on the name rather than by resolving it to a file, so it holds even
    when the imported module's source is outside the scanned file list. Whole
    segments only: ``app.website.render`` is not ``web``.
    """
    return any(
        part.lower() in OUTER_LAYER_DIRS
        for part in (module or "").split(".")
        if part
    )


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
