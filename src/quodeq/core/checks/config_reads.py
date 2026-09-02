"""Configuration read from an inner layer -- CLEA-DEP-07.

"Configuration and environment variables are not read in inner layers." The
requirement is easy to state and easy to miss by eye, because the environment
reaches the inner layer under a dozen spellings: ``os.environ``, an aliased
``import os as o``, ``from os import getenv``, or a config package that hides
the read behind its own API. A text search finds the first spelling and misses
the rest; parsed and alias-resolved, they all look the same.

Business rules that read their own configuration cannot be instantiated twice
with different settings, which is the practical cost the requirement is about.
"""
from __future__ import annotations

from collections.abc import Sequence

from quodeq.core.checks._judgments import compliance, violation
from quodeq.core.checks.layers import inner_layer_files
from quodeq.core.checks.model import ImportGraph, SymbolUse, top_level
from quodeq.core.events.models import Judgment

REQ = "CLEA-DEP-07"

# Dotted names whose use means "this code reads its environment".
CONFIG_SYMBOLS = frozenset({
    "os.environ", "os.environb", "os.getenv", "os.getenvb", "os.putenv",
})

# Packages that exist to load configuration. Importing one into an inner layer
# is the same defect as reading os.environ there, one level of indirection up.
CONFIG_PACKAGES = frozenset({
    "dotenv", "configparser", "dynaconf", "decouple", "environs",
    "pydantic_settings", "hydra", "omegaconf",
})


def _collect_config_reads(
    graph: ImportGraph, symbol_uses: Sequence[SymbolUse], inner_set: set[str],
) -> dict[tuple[str, str], int]:
    """First line per (file, source) where an inner-layer file reads config.

    One finding per (file, source): three os.environ reads in one module are
    one dependency on the environment.
    """
    first_line: dict[tuple[str, str], int] = {}

    def note(file: str, source: str, line: int) -> None:
        key = (file, source)
        first_line[key] = min(first_line.get(key, line), line)

    for use in symbol_uses:
        if use.file in inner_set and use.symbol in CONFIG_SYMBOLS:
            note(use.file, use.symbol, use.line)
    for edge in graph.edges:
        if edge.file in inner_set and top_level(edge.module) in CONFIG_PACKAGES:
            note(edge.file, top_level(edge.module), edge.line)
    return first_line


def _build_config_read_judgments(
    dimension: str, inner: list[str], first_line: dict[tuple[str, str], int],
) -> list[Judgment]:
    judgments = [
        violation(
            req=REQ, dimension=dimension, file=file, line=line,
            title=f"Inner layer reads configuration via '{source}'",
            reason=(
                f"This file is in an inner layer and reads configuration "
                f"through '{source}'. Business rules that fetch their own "
                f"settings cannot be run twice with different ones: pass the "
                f"values in from the layer that owns them."
            ),
        )
        for (file, source), line in first_line.items()
    ]
    if not judgments:
        count = len(inner)
        label = "file" if count == 1 else "files"
        judgments.append(compliance(
            req=REQ, dimension=dimension, anchor=inner[0],
            title="Inner layers do not read configuration",
            reason=(
                f"Checked {count} inner-layer {label}: none reads the "
                f"environment or imports a configuration package."
            ),
        ))
    judgments.sort(key=lambda j: (j.file, j.line))
    return judgments


def check_config_reads(
    graph: ImportGraph,
    symbol_uses: Sequence[SymbolUse],
    *,
    dimension: str,
) -> list[Judgment]:
    """Judge CLEA-DEP-07 against *graph* and the resolved *symbol_uses*.

    Empty when the project has no recognisable inner layer.
    """
    known = graph.files() | {u.file for u in symbol_uses}
    inner = sorted(inner_layer_files(known))
    if not inner:
        return []

    first_line = _collect_config_reads(graph, symbol_uses, set(inner))
    return _build_config_read_judgments(dimension, inner, first_line)
