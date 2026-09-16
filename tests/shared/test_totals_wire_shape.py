"""Totals.violations_per100_files must camelize to violationsPer100Files on the wire.

_CAMEL_RE doesn't uppercase after a digit, so a field literally named
``violations_per_100_files`` serialized as ``violationsPer_100Files`` -- a
mismatch with the report JSON and the UI, which both expect
``violationsPer100Files``. The fix is the dataclass field's own name
(``violations_per100_files``), not a wider regex.
"""
from __future__ import annotations

from quodeq.core.types.dimension import DimensionResult
from quodeq.core.types.finding import SeverityTally, Totals
from quodeq.shared.serialization import to_camel_dict


def test_density_reaches_the_wire_under_the_report_key():
    dim = DimensionResult(dimension="reliability", totals=Totals(
        violation_count=3, compliance_count=0, severity=SeverityTally(), violations_per100_files=37.5,
    ))
    totals = to_camel_dict(dim)["totals"]
    assert totals["violationsPer100Files"] == 37.5
    assert "violationsPer_100Files" not in totals
