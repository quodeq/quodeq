"""Framework packages reaching the inner layers -- CLEA-FRM-01 / CLEA-DEP-06.

Two requirements, one traversal of the import graph:

* **CLEA-FRM-01** -- an inner-layer file imports a framework package itself.
* **CLEA-DEP-06** -- an inner-layer file reaches a framework package *through
  a first-party module that is not itself inner-layer*. This is the standard's
  own example ("entity A imports utility B, utility B imports Flask") and the
  reason a per-file scan can never judge it: nothing in A names Flask.

The "not itself inner-layer" clause is what keeps the transitive rule usable.
When the path runs through another inner file, that file already carries its
own FRM-01 violation; repeating the fact at every downstream importer turns
one defect into dozens of findings and buries the single place to fix it.
"""
from __future__ import annotations

from collections import deque

from quodeq.core.checks._judgments import compliance, violation
from quodeq.core.checks.layers import is_inner_layer_path
from quodeq.core.checks.model import ImportEdge, ImportGraph, top_level
from quodeq.core.events.models import Judgment

REQ_DIRECT = "CLEA-FRM-01"
REQ_TRANSITIVE = "CLEA-DEP-06"
_SOURCE_SUFFIXES = (".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")


def _module_name(path: str, first_party: frozenset[str]) -> str | None:
    """Dotted module name for a source *path*, or None if it is not first-party.

    Resolution is by convention: drop the extension, then keep the segments
    from the first one that names a first-party package. ``src/app/utils.py``
    with ``first_party={"app"}`` yields ``app.utils``; a path that never
    mentions a first-party package yields None, because we would be guessing.
    """
    normalized = path.replace("\\", "/")
    for suffix in _SOURCE_SUFFIXES:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    segments = [s for s in normalized.split("/") if s]
    if segments and segments[-1] == "__init__":
        segments.pop()
    for i, segment in enumerate(segments):
        if segment in first_party:
            return ".".join(segments[i:])
    return None


def _index(graph: ImportGraph) -> tuple[dict[str, list[ImportEdge]], dict[str, str]]:
    """Return (imports by file, file by module name)."""
    by_file: dict[str, list[ImportEdge]] = {}
    for edge in graph.edges:
        by_file.setdefault(edge.file, []).append(edge)
    by_module: dict[str, str] = {}
    for path in by_file:
        module = _module_name(path, graph.first_party)
        if module is not None:
            by_module[module] = path
    return by_file, by_module


def _resolve(module: str, by_module: dict[str, str]) -> str | None:
    """The first-party file a dotted *module* refers to, if we have its source.

    ``app.utils.text.slugify`` imports a name out of ``app.utils.text``, so
    walk the dotted name down until it matches a module we know.
    """
    parts = module.split(".")
    while parts:
        hit = by_module.get(".".join(parts))
        if hit is not None:
            return hit
        parts.pop()
    return None


def _direct_frameworks(
    edges: list[ImportEdge], framework_packages: frozenset[str],
) -> dict[str, int]:
    """{framework package: earliest line importing it} for one file."""
    found: dict[str, int] = {}
    for edge in edges:
        package = top_level(edge.module)
        if package in framework_packages:
            found[package] = min(found.get(package, edge.line), edge.line)
    return found


def _transitive_frameworks(
    origin: str,
    by_file: dict[str, list[ImportEdge]],
    by_module: dict[str, str],
    framework_packages: frozenset[str],
    first_party: frozenset[str],
) -> dict[str, tuple[int, str]]:
    """{framework package: (line in *origin*, path description)} reached indirectly.

    Breadth-first so the recorded path is the shortest one, which is the most
    readable explanation of why the dependency exists. Inner-layer files are
    never traversed: they carry their own findings.
    """
    found: dict[str, tuple[int, str]] = {}
    seen = {origin}
    queue: deque[tuple[str, int, list[str]]] = deque()
    for edge in by_file.get(origin, ()):
        if top_level(edge.module) not in first_party:
            continue
        target = _resolve(edge.module, by_module)
        if target is None or target in seen or is_inner_layer_path(target):
            continue
        seen.add(target)
        queue.append((target, edge.line, [edge.module]))

    while queue:
        current, origin_line, chain = queue.popleft()
        edges = by_file.get(current, [])
        for package in _direct_frameworks(edges, framework_packages):
            if package not in found:
                found[package] = (origin_line, " -> ".join([*chain, package]))
        for edge in edges:
            if top_level(edge.module) not in first_party:
                continue
            target = _resolve(edge.module, by_module)
            if target is None or target in seen or is_inner_layer_path(target):
                continue
            seen.add(target)
            queue.append((target, origin_line, [*chain, edge.module]))
    return found


def _clean_report(req: str, dimension: str, anchor: str, checked: int) -> Judgment:
    """One compliance for a requirement the check covered and found clean."""
    label = "file" if checked == 1 else "files"
    return compliance(
        req=req, dimension=dimension, anchor=anchor,
        title="Inner layers are free of framework dependencies",
        reason=(
            f"Checked the import graph of {checked} inner-layer {label}: none "
            f"imports a framework package, directly or through another "
            f"first-party module."
        ),
    )


def _file_framework_judgments(
    file: str,
    by_file: dict[str, list[ImportEdge]],
    by_module: dict[str, str],
    framework_packages: frozenset[str],
    first_party: frozenset[str],
    dimension: str,
) -> list[Judgment]:
    """Direct + transitive framework-dependency judgments for one inner file."""
    judgments: list[Judgment] = []
    direct = _direct_frameworks(by_file[file], framework_packages)
    for package in sorted(direct):
        judgments.append(violation(
            req=REQ_DIRECT, dimension=dimension, file=file, line=direct[package],
            title=f"Inner layer imports framework package '{package}'",
            reason=(
                f"This file is in an inner layer and imports the framework "
                f"package '{package}' directly. Clean Architecture keeps "
                f"frameworks at the edges: business rules must not depend on "
                f"the delivery mechanism."
            ),
        ))
    transitive = _transitive_frameworks(
        file, by_file, by_module, framework_packages, first_party,
    )
    for package in sorted(transitive):
        if package in direct:
            continue  # already billed once, as a direct import
        line, path = transitive[package]
        judgments.append(violation(
            req=REQ_TRANSITIVE, dimension=dimension, file=file, line=line,
            title=f"Inner layer depends on framework '{package}' transitively",
            reason=(
                f"This file is in an inner layer and reaches the framework "
                f"package '{package}' through {path}. Nothing in this file "
                f"names '{package}', so the dependency is invisible when "
                f"reading it, but the inner layer cannot be built or tested "
                f"without the framework."
            ),
        ))
    return judgments


def check_framework_dependencies(
    graph: ImportGraph,
    *,
    framework_packages: frozenset[str],
    dimension: str,
) -> list[Judgment]:
    """Judge CLEA-FRM-01 and CLEA-DEP-06 against *graph*.

    Returns an empty list when the project has no recognisable inner layer or
    no framework list -- there is nothing to judge, and inventing findings from
    an unreadable layout is worse than staying quiet.
    """
    if not graph.edges or not framework_packages:
        return []
    by_file, by_module = _index(graph)
    inner = sorted(f for f in by_file if is_inner_layer_path(f))
    if not inner:
        return []

    judgments: list[Judgment] = []
    for file in inner:
        judgments += _file_framework_judgments(
            file, by_file, by_module, framework_packages, graph.first_party, dimension,
        )
    # A requirement the traversal covered without finding anything is clean,
    # and saying so is the difference between "measured" and "never looked".
    violated = {j.practice_id for j in judgments}
    for req in (REQ_DIRECT, REQ_TRANSITIVE):
        if req not in violated:
            judgments.append(_clean_report(req, dimension, inner[0], len(inner)))

    judgments.sort(key=lambda j: (j.file, j.practice_id, j.line))
    return judgments
