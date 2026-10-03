"""Integer fields on the findings wire dict are coerced, never raised on."""
from quodeq.data.sqlite.row_mappers import finding_dict_to_row

_BASE = {"p": "FT", "t": "violation", "severity": "minor", "file": "a.py"}


def test_an_infinite_line_and_a_junk_schema_version_map_to_defaults():
    row = finding_dict_to_row({**_BASE, "line": 1e400, "end_line": 1e400, "schema_version": "x"})
    assert (row["line"], row["end_line"], row["schema_version"]) == (0, 0, 1)


def test_valid_integer_fields_map_as_given():
    row = finding_dict_to_row({**_BASE, "line": 10, "end_line": "12", "schema_version": 2})
    assert (row["line"], row["end_line"], row["schema_version"]) == (10, 12, 2)
    assert row["dedup_key"] == "FT|a.py|10|violation"


def test_absent_integer_fields_map_to_defaults():
    row = finding_dict_to_row(dict(_BASE))
    assert (row["line"], row["end_line"], row["schema_version"]) == (0, 0, 1)
