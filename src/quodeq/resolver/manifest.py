"""Manifest builder.

Given a FindingInput and an IndexCache, produces a complete Manifest by
combining index queries (cross-file facts) with same-file tree-sitter
extraction (shape patterns and the enclosing function tree).
"""

from __future__ import annotations

from pathlib import Path

from quodeq.resolver.cache import IndexCache
from quodeq.resolver.languages.python import PythonAdapter
from quodeq.resolver.models import FindingInput, Location, Manifest
from quodeq.resolver.path_role import classify_path_role
from quodeq.resolver.queries import (
    callers_of,
    param_type_users,
    subclasses_of,
    where_defined,
)
from quodeq.resolver.registry import get_adapter_for
from quodeq.resolver.shape import enclosing_function, find_or_seam


_PROTOCOL_BASE_NAMES = frozenset({"Protocol", "ABC", "ABCMeta"})


def build_manifest(
    cache: IndexCache, project_root: Path, finding: FindingInput
) -> Manifest:
    project_root = project_root.resolve()
    target_path = project_root / finding.file
    source = target_path.read_bytes()
    adapter = get_adapter_for(target_path)
    if not isinstance(adapter, PythonAdapter):
        # Only Python is implemented in Plan 1; other adapters return a minimal manifest.
        return Manifest(
            target_file=finding.file,
            target_line=finding.line,
            target_file_role=classify_path_role(finding.file),
        )

    manifest = Manifest(
        target_file=finding.file,
        target_line=finding.line,
        target_file_role=classify_path_role(finding.file),
    )

    # Resolve the referenced symbol. First try imports on the cited line
    # (covers findings that point directly at an import). If nothing matches,
    # fall back to scanning imports inside the enclosing function: real
    # findings rarely cite the import line itself — they cite a docstring,
    # signature line, or call site inside the function that uses the
    # concrete class.
    result = adapter.parse(source)
    cited_imports = [i for i in result.imports if i.line == finding.line]
    if cited_imports:
        manifest.referenced_symbol = cited_imports[0].imported_name
    else:
        candidate = _pick_referenced_symbol_in_scope(
            cache, result.imports, result.functions, finding.line
        )
        if candidate:
            manifest.referenced_symbol = candidate

    if manifest.referenced_symbol:
        manifest.referenced_symbol_defined_at = where_defined(
            cache, manifest.referenced_symbol, kind="class"
        )
        manifest.referenced_symbol_bases = _bases_for(
            cache, manifest.referenced_symbol
        )

    # Pick the abstraction: the rightmost base whose own definition has Protocol/ABC in its bases.
    abstraction = _pick_abstraction(cache, manifest.referenced_symbol_bases)
    if abstraction:
        manifest.abstraction = abstraction
        manifest.abstraction_defined_at = where_defined(cache, abstraction, kind="class")
        manifest.abstraction_kind = _classify_abstraction_kind(cache, abstraction)
        prod, test = _count_implementations(cache, abstraction)
        manifest.abstraction_implementations_prod = prod
        manifest.abstraction_implementations_test_stubs = test
        manifest.abstraction_used_as_parameter_type_in = param_type_users(cache, abstraction)

    # Same-file shape: enclosing function + parent function + seam.
    enclosing = enclosing_function(adapter, source, finding.line)
    if enclosing:
        enclosing.file = finding.file
        manifest.target_enclosing_function = enclosing
        callers = callers_of(cache, enclosing.name)
        manifest.enclosing_function_called_from = callers

        # Parent: the function whose body contains the call to the enclosing function.
        for caller in callers:
            if caller.file == finding.file:
                caller_path = project_root / caller.file
                caller_src = caller_path.read_bytes()
                parent_fn = enclosing_function(adapter, caller_src, caller.line)
                if parent_fn:
                    parent_fn.file = finding.file
                    manifest.target_parent_function = parent_fn
                    seam = find_or_seam(adapter, caller_src, parent_fn.name)
                    if seam:
                        seam_line, seam_pattern = seam
                        manifest.target_parent_seam_at = Location(
                            file=finding.file, line=seam_line
                        )
                        manifest.target_parent_seam_pattern = seam_pattern
                break

    return manifest


def _pick_referenced_symbol_in_scope(
    cache: IndexCache,
    imports: list,
    functions: list,
    target_line: int,
) -> str | None:
    """Find the concrete class an enclosing-function import most likely refers to.

    Many real findings cite a line inside a function body (docstring, return
    type annotation, call site) rather than the import line itself. This
    walks imports whose line falls inside the enclosing function's span and
    picks the one whose `imported_name` looks like a concrete class that
    implements an abstraction.

    Returns the imported_name to use as ``manifest.referenced_symbol``, or
    ``None`` if no in-scope import has cross-file bases registered.

    Scoring (best first):
      1. Imported class has bases that include a Protocol/ABC ancestor.
      2. Imported class has *any* bases recorded in the index.
      3. (Skip — no cross-file evidence to support a verdict.)
    """
    # Bound the enclosing function: the next def whose line > target_line
    # marks where the enclosing function ends (good enough without nested
    # function tracking; nested functions inside the body would still be
    # inside the enclosing span).
    sorted_starts = sorted(fn.line for fn in functions)
    enclosing_start = None
    for start in sorted_starts:
        if start <= target_line:
            enclosing_start = start
        else:
            break
    if enclosing_start is None:
        return None
    scope_end = None
    for start in sorted_starts:
        if start > enclosing_start:
            scope_end = start
            break

    in_scope_imports = [
        i for i in imports
        if i.line >= enclosing_start and (scope_end is None or i.line < scope_end)
    ]
    if not in_scope_imports:
        return None

    best_with_abstraction: str | None = None
    best_with_any_bases: str | None = None
    for imp in in_scope_imports:
        bases = _bases_for(cache, imp.imported_name)
        if not bases:
            continue
        if best_with_any_bases is None:
            best_with_any_bases = imp.imported_name
        if any(
            n in _PROTOCOL_BASE_NAMES
            for base in bases
            for n in _bases_for(cache, base) + [base]
        ):
            best_with_abstraction = imp.imported_name
            break  # first match wins; lazy imports are typically the DI candidate

    return best_with_abstraction or best_with_any_bases


def _bases_for(cache: IndexCache, class_name: str) -> list[str]:
    rows = cache.execute(
        "SELECT base_list FROM classes WHERE name = ? LIMIT 1", (class_name,)
    )
    if not rows:
        return []
    return [b.strip() for b in rows[0]["base_list"].split(",") if b.strip()]


def _pick_abstraction(cache: IndexCache, bases: list[str]) -> str | None:
    """Pick the base most likely to be the abstraction.

    Prefer the rightmost base whose own bases include Protocol/ABC; fall back
    to the rightmost base named ActionProvider-style.
    """
    for base in reversed(bases):
        own_bases = _bases_for(cache, base)
        if any(n in _PROTOCOL_BASE_NAMES for n in own_bases):
            return base
    return bases[-1] if bases else None


def _classify_abstraction_kind(cache: IndexCache, name: str) -> str | None:
    own_bases = _bases_for(cache, name)
    if "Protocol" in own_bases:
        return "Protocol"
    if "ABC" in own_bases or "ABCMeta" in own_bases:
        return "ABC"
    return None


def _count_implementations(cache: IndexCache, abstraction: str) -> tuple[int, int]:
    """Return (prod_count, test_stub_count) implementations of the abstraction."""
    subs = subclasses_of(cache, abstraction)
    prod = sum(1 for s in subs if classify_path_role(s.file) != "test")
    test = sum(1 for s in subs if classify_path_role(s.file) == "test")
    return prod, test
