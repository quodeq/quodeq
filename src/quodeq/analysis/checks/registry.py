"""Name -> checker lookup, and the facts they share.

A requirement opts into a checker by naming it in the compiled standard
(``"check": "framework-imports"``). Standards ship as data and outlive the
binaries that read them, so a name this build does not recognise is ignored
rather than treated as an error: an older quodeq reading a newer standard
loses that check and keeps everything else.

Every checker reads the same import graph. Parsing it once per context, and
only when a checker actually asks, keeps three checkers from walking the tree
three times without paying for facts nobody wanted.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from quodeq.core.checks.config_reads import CONFIG_SYMBOLS, check_config_reads
from quodeq.core.checks.entity_imports import check_entity_imports
from quodeq.core.checks.framework_deps import check_framework_dependencies
from quodeq.core.checks.frameworks import FRAMEWORK_PACKAGES
from quodeq.core.checks.model import ImportGraph, SymbolUse
from quodeq.core.events.models import Judgment


@dataclass(frozen=True)
class CheckContext:
    """What every checker gets: the project, its sources, and the dimension.

    Also memoises the parsed facts, so several checkers over one context share
    a single walk of the tree. The cache lives on the context rather than in a
    module global: it is then scoped to the call that created it, and two
    projects can never see each other's graph.

    The disk-touching builders are injected by the composition point
    (``runner.deterministic_judgments`` passes the ``data.fs`` ones), so this
    module stays a pure consumer of the graph and a test can hand in an
    in-memory graph without patching.
    """
    root: Path
    source_files: Sequence[str]
    dimension: str
    graph_builder: Callable[[Path, Iterable[Path]], ImportGraph] | None = None
    symbol_uses_builder: (
        Callable[[Path, Iterable[Path], frozenset[str]], tuple[SymbolUse, ...]] | None
    ) = None
    _cache: dict = field(default_factory=dict, repr=False, compare=False)

    def _paths(self) -> list[Path]:
        return [Path(f) for f in self.source_files]

    def graph(self) -> ImportGraph:
        if "graph" not in self._cache:
            if self.graph_builder is None:
                raise RuntimeError(
                    "CheckContext has no graph_builder; the composition point "
                    "must inject one (see runner.deterministic_judgments)")
            self._cache["graph"] = self.graph_builder(self.root, self._paths())
        return self._cache["graph"]

    def config_symbol_uses(self) -> tuple[SymbolUse, ...]:
        if "uses" not in self._cache:
            if self.symbol_uses_builder is None:
                raise RuntimeError(
                    "CheckContext has no symbol_uses_builder; the composition "
                    "point must inject one (see runner.deterministic_judgments)")
            self._cache["uses"] = self.symbol_uses_builder(
                self.root, self._paths(), CONFIG_SYMBOLS,
            )
        return self._cache["uses"]


def _framework_imports(context: CheckContext) -> list[Judgment]:
    return check_framework_dependencies(
        context.graph(),
        framework_packages=FRAMEWORK_PACKAGES,
        dimension=context.dimension,
    )


def _entity_imports(context: CheckContext) -> list[Judgment]:
    return check_entity_imports(context.graph(), dimension=context.dimension)


def _config_reads(context: CheckContext) -> list[Judgment]:
    return check_config_reads(
        context.graph(), context.config_symbol_uses(), dimension=context.dimension,
    )


CHECKERS: dict[str, Callable[[CheckContext], list[Judgment]]] = {
    "framework-imports": _framework_imports,
    "entity-imports": _entity_imports,
    "config-reads": _config_reads,
}
