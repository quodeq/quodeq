"""Projection places every finding event through admission.

The event log holds what was reported; the derived fields in an event are
whatever its writer knew at the time. Projection re-admits each finding with
the installed standards, so ``evaluation.db`` always agrees with the current
standard, and a finding the standard cannot place goes to
``unmapped_findings`` instead of being graded under a blank principle.
"""
from __future__ import annotations

import dataclasses
import threading
from collections.abc import Callable
from pathlib import Path

from quodeq.core.admission import (
    Admitted, FindingFacts, StandardCatalog, Unmapped, UnmappedReason, admit,
)
from quodeq.core.events.models import Judgment
from quodeq.data.fs.standard_index_loader import load_standard_catalog
from quodeq.data.projection.standards_defaults import default_standards_dirs

Admitter = Callable[[Judgment], "Admitted | Unmapped"]

_memo_lock = threading.Lock()
_memo: dict[tuple, StandardCatalog] = {}


def _standard_files(*dirs: Path | None) -> tuple[tuple[str, int, int], ...]:
    stamps = []
    for directory in dirs:
        if directory is None or not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            try:
                st = path.stat()
            except OSError:
                continue
            stamps.append((str(path), st.st_mtime_ns, st.st_size))
    return tuple(stamps)


def installed_catalog(
    compiled_dir: Path | None = None, evaluators_dir: Path | None = None,
) -> StandardCatalog:
    """Every installed standard, re-read only when one of its files changes."""
    if compiled_dir is None and evaluators_dir is None:
        compiled_dir, evaluators_dir = default_standards_dirs()
    key = _standard_files(compiled_dir, evaluators_dir)
    with _memo_lock:
        hit = _memo.get(key)
    if hit is not None:
        return hit
    dimensions = sorted({Path(p).stem for p, _m, _s in key})
    catalog = load_standard_catalog(dimensions, evaluators_dir=evaluators_dir, compiled_dir=compiled_dir)
    with _memo_lock:
        _memo.clear()
        _memo[key] = catalog
    return catalog


def _facts(j: Judgment) -> FindingFacts:
    return FindingFacts(
        req=j.req or None, verdict=j.verdict, dimension=j.dimension or None,
        file=j.file, line=j.line, end_line=j.end_line, snippet=j.snippet, reason=j.reason,
        title=j.title, scope=j.scope, severity=j.severity, confidence=j.confidence,
        violation_type=j.violation_type_raw or j.violation_type, cwe=j.cwe,
        principle_hint=j.practice_id or None,
    )


def make_admitter(catalog_fn: Callable[[], StandardCatalog] | None = None) -> Admitter:
    """An admitter reading the catalog on every call (it is memoized on the files).

    Without *catalog_fn* it reads ``installed_catalog`` from this module at
    call time, so the test suite can swap the installed standards out.

    A finding is placed within the dimension its writer recorded and never
    rerouted: writers route at write time where a scan covers several
    dimensions, and the per-dimension report reads each dimension's own
    evidence, so rerouting here would count a finding on the dashboard that
    the CLI report quarantines.
    """
    def admit_judgment(j: Judgment) -> Admitted | Unmapped:
        catalog = catalog_fn() if catalog_fn is not None else installed_catalog()
        return admit(_facts(j), catalog.only([j.dimension or ""]), j.dimension or None)
    return admit_judgment


def placed(j: Judgment, result: Admitted) -> Judgment:
    """*j* with the principle, requirement and dimension admission derived."""
    return dataclasses.replace(
        j, practice_id=result.principle, req=result.req or j.req, dimension=result.dimension,
    )


def unmapped_reason(j: Judgment, result: Admitted | Unmapped) -> str | None:
    """Why *j* goes to ``unmapped_findings``, or None when it can be stored.

    With no loaded standard a judgment is stored as reported, if it names a
    principle; one with none is unmapped either way.
    """
    if isinstance(result, Admitted):
        return None
    if result.reason is UnmappedReason.NO_STANDARD and j.practice_id:
        return None
    return result.reason.value


def mapping_stamps(dimensions: set[str] | list[str]) -> dict[str, str]:
    """The current mapping stamp of each dimension's standard ("" when none is installed)."""
    catalog = installed_catalog()
    out: dict[str, str] = {}
    for dimension in dimensions:
        index = catalog.get(dimension)
        out[dimension] = index.mapping_stamp if index is not None else ""
    return out
