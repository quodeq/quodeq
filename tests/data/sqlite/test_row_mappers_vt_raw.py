"""violation_type_raw round-trips through the row-mapper functions."""
from quodeq.core.events.models import Judgment
from quodeq.data.sqlite.row_mappers import (
    finding_dict_to_row,
    judgment_to_row,
    row_to_finding,
)


def test_vt_raw_maps_to_violation_type_raw_and_back():
    row = finding_dict_to_row({
        "p": "FT", "t": "violation", "severity": "minor", "file": "a.py", "line": 1,
        "vt": "Empty_Catch", "vt_raw": "Empty_Catch",
    })
    assert row["violation_type_raw"] == "Empty_Catch"
    assert row_to_finding(row).violation_type_raw == "Empty_Catch"


def test_missing_vt_raw_stores_empty_and_reads_none():
    row = finding_dict_to_row({"p": "FT", "t": "violation", "severity": "minor",
                               "file": "a.py", "line": 1})
    assert row["violation_type_raw"] == ""
    assert row_to_finding(row).violation_type_raw is None


def test_judgment_to_row_carries_violation_type_raw():
    j = Judgment(practice_id="FT", verdict="violation", dimension="reliability",
                 file="a.py", line=1, reason="why", violation_type_raw="X")
    assert judgment_to_row(j)["violation_type_raw"] == "X"
