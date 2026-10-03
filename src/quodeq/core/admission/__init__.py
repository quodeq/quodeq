"""Finding admission: the one place a reported finding meets its standard.

A finding is two kinds of data. Facts are what the model or a checker
reported (requirement code, location, snippet, reason, severity). Derived data
comes from the standard (canonical requirement, principle, dimension, refs).
``admit`` is the only function that derives it, and it never returns a partial
result: a finding is either ``Admitted`` with every derived field set, or
``Unmapped`` with the reason.
"""
from __future__ import annotations

from quodeq.core.admission.admit import admit
from quodeq.core.admission.facts import FindingFacts
from quodeq.core.admission.index import StandardCatalog, StandardIndex
from quodeq.core.admission.result import Admitted, Unmapped, UnmappedReason

__all__ = [
    "Admitted",
    "FindingFacts",
    "StandardCatalog",
    "StandardIndex",
    "Unmapped",
    "UnmappedReason",
    "admit",
]
