"""Static facts a checker reasons about."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ImportEdge:
    """One import statement: *file* imports *module* at *line*.

    ``module`` is the dotted name as written in the source
    (``pydantic.fields``, ``app.utils.text``), not a resolved file path --
    resolution needs the project layout and belongs to whoever built the
    graph.
    """
    file: str
    line: int
    module: str


@dataclass(frozen=True)
class ImportGraph:
    """Every intra-project import edge, plus which packages are first-party.

    ``first_party`` holds top-level package names owned by the project
    (``{"quodeq"}``, ``{"app", "lib"}``). Anything else is a dependency whose
    source we cannot see, so a checker must not traverse through it.
    """
    edges: tuple[ImportEdge, ...] = ()
    first_party: frozenset[str] = field(default_factory=frozenset)

    def files(self) -> frozenset[str]:
        """Every file that imports something."""
        return frozenset(e.file for e in self.edges)


def top_level(module: str) -> str:
    """The root package of a dotted module name (``a.b.c`` -> ``a``)."""
    return (module or "").split(".", 1)[0]
