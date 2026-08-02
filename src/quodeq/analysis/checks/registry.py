"""Name -> checker lookup.

A requirement opts into a checker by naming it in the compiled standard
(``"check": "framework-imports"``). Standards ship as data and outlive the
binaries that read them, so a name this build does not recognise is ignored
rather than treated as an error: an older quodeq reading a newer standard
loses that check and keeps everything else.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from quodeq.core.checks.framework_deps import check_framework_dependencies
from quodeq.core.checks.frameworks import FRAMEWORK_PACKAGES
from quodeq.core.events.models import Judgment
from quodeq.data.fs.import_graph import build_import_graph


@dataclass(frozen=True)
class CheckContext:
    """What every checker gets: the project, its sources, and the dimension."""
    root: Path
    source_files: Sequence[str]
    dimension: str


def _framework_imports(context: CheckContext) -> list[Judgment]:
    graph = build_import_graph(
        context.root, [Path(f) for f in context.source_files],
    )
    return check_framework_dependencies(
        graph,
        framework_packages=FRAMEWORK_PACKAGES,
        dimension=context.dimension,
    )


CHECKERS: dict[str, Callable[[CheckContext], list[Judgment]]] = {
    "framework-imports": _framework_imports,
}
