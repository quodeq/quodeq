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

    # Resolve the referenced symbol from the cited line's import statement.
    result = adapter.parse(source)
    cited_imports = [i for i in result.imports if i.line == finding.line]
    if cited_imports:
        manifest.referenced_symbol = cited_imports[0].imported_name

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


def _bases_for(cache: IndexCache, class_name: str) -> list[str]:
    row = cache.conn.execute(
        "SELECT base_list FROM classes WHERE name = ? LIMIT 1", (class_name,)
    ).fetchone()
    if not row:
        return []
    return [b.strip() for b in row["base_list"].split(",") if b.strip()]


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
