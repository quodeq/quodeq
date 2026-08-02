"""Entities importing outward -- CLEA-DEP-02.

"Entities must not import from use case or adapter layers." A per-file pass can
see the import statement but not what the imported module *is*: whether
``app.gateways.orders`` is an adapter or just a badly named domain helper is a
question about the project's shape, and shape is what a graph has.

Judged on the imported module's dotted name rather than by resolving it to a
file, so the verdict holds even when that module's source is outside the
scanned file list -- which is the normal case for anything the scan skipped.

Scope is entities specifically, not every inner layer. A use case reaching an
adapter is the inward rule (CLEA-DEP-01), and reporting it here would file one
requirement's finding under another's ID.
"""
from __future__ import annotations

from quodeq.core.checks._judgments import compliance, violation
from quodeq.core.checks.layers import is_entity_layer_path, is_outer_layer_module
from quodeq.core.checks.model import ImportGraph, top_level
from quodeq.core.events.models import Judgment

REQ = "CLEA-DEP-02"


def check_entity_imports(graph: ImportGraph, *, dimension: str) -> list[Judgment]:
    """Judge CLEA-DEP-02 against *graph*.

    Empty when the project has no directory we can name as its entity layer:
    an unnameable layer is one we have no standing to judge.
    """
    entities = sorted(f for f in graph.files() if is_entity_layer_path(f))
    if not entities:
        return []

    entity_set = set(entities)
    # One finding per (entity file, target module): ten imports of the same
    # adapter are one dependency, and the fix is the same edit.
    first_line: dict[tuple[str, str], int] = {}
    for edge in graph.edges:
        if edge.file not in entity_set:
            continue
        if top_level(edge.module) not in graph.first_party:
            continue  # third-party is a framework question (CLEA-FRM-01)
        if not is_outer_layer_module(edge.module):
            continue
        key = (edge.file, edge.module)
        first_line[key] = min(first_line.get(key, edge.line), edge.line)

    judgments = [
        violation(
            req=REQ, dimension=dimension, file=file, line=line,
            title=f"Entity layer imports '{module}'",
            reason=(
                f"This file is in the entity layer and imports '{module}', "
                f"which lives in an outer layer. Dependencies point inward: "
                f"entities must be usable without the adapters and delivery "
                f"mechanisms built on top of them."
            ),
        )
        for (file, module), line in first_line.items()
    ]
    if not judgments:
        count = len(entities)
        label = "file" if count == 1 else "files"
        judgments.append(compliance(
            req=REQ, dimension=dimension, anchor=entities[0],
            title="Entity layer has no outward dependencies",
            reason=(
                f"Checked the imports of {count} entity-layer {label}: none "
                f"reaches a use case, adapter or infrastructure package."
            ),
        ))
    judgments.sort(key=lambda j: (j.file, j.line))
    return judgments
