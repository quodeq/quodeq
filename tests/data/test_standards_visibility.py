import json
from pathlib import Path

import pytest

from quodeq.core.standards.visibility import (
    DEFAULT_VISIBLE_STANDARDS,
    VISIBILITY_RELPATH,
    partition_visible,
    validate_visible_ids,
)
from quodeq.data.fs.standards_prefs import (
    load_visible_standard_ids,
    save_visible_standard_ids,
)


def test_defaults_are_the_six_iso_dimensions():
    assert DEFAULT_VISIBLE_STANDARDS == (
        "security", "reliability", "maintainability",
        "performance", "usability", "flexibility",
    )


def test_absent_file_yields_defaults(tmp_path):
    assert load_visible_standard_ids(tmp_path) == DEFAULT_VISIBLE_STANDARDS


def test_none_root_yields_defaults():
    assert load_visible_standard_ids(None) == DEFAULT_VISIBLE_STANDARDS


def test_saved_selection_round_trips(tmp_path):
    save_visible_standard_ids(tmp_path, ["security", "clean-architecture"])
    assert load_visible_standard_ids(tmp_path) == ("security", "clean-architecture")


def test_saved_file_shape_is_versioned(tmp_path):
    save_visible_standard_ids(tmp_path, ["security"])
    data = json.loads((tmp_path / VISIBILITY_RELPATH).read_text(encoding="utf-8"))
    assert data == {"version": 1, "visibleStandardIds": ["security"]}


def test_empty_selection_round_trips_as_empty(tmp_path):
    # An explicit "hide everything" is a real state and must NOT read back as
    # the defaults -- otherwise the user cannot deselect the last standard.
    save_visible_standard_ids(tmp_path, [])
    assert load_visible_standard_ids(tmp_path) == ()


def test_ids_are_normalized_to_lowercase(tmp_path):
    save_visible_standard_ids(tmp_path, ["Security", "CLEAN-Architecture"])
    assert load_visible_standard_ids(tmp_path) == ("security", "clean-architecture")


@pytest.mark.parametrize("body", ["not json{", '{"version": 1}', '{"visibleStandardIds": "x"}', "[]"])
def test_malformed_file_degrades_to_defaults(tmp_path, body):
    path = tmp_path / VISIBILITY_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    assert load_visible_standard_ids(tmp_path) == DEFAULT_VISIBLE_STANDARDS


def test_non_string_entries_are_dropped(tmp_path):
    path = tmp_path / VISIBILITY_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "visibleStandardIds": ["security", 3, None]}),
                    encoding="utf-8")
    assert load_visible_standard_ids(tmp_path) == ("security",)


def test_validate_accepts_known_ids():
    clean, errors = validate_visible_ids(["security"], {"security", "reliability"})
    assert (clean, errors) == (["security"], [])


def test_validate_rejects_unknown_id():
    clean, errors = validate_visible_ids(["nope"], {"security"})
    assert clean == []
    assert errors == ["nope: unknown standard"]


def test_validate_rejects_non_list():
    clean, errors = validate_visible_ids({"a": 1}, {"security"})
    assert clean == []
    assert errors == ["visibleStandardIds must be an array"]


def test_validate_deduplicates_preserving_order():
    clean, errors = validate_visible_ids(
        ["reliability", "security", "reliability"], {"security", "reliability"})
    assert (clean, errors) == (["reliability", "security"], [])


def test_partition_splits_visible_and_hidden():
    visible, hidden = partition_visible(
        ["Security", "clean-architecture"], ("security",))
    assert visible == ["Security"]
    assert hidden == ["clean-architecture"]


def test_partition_with_none_hides_nothing():
    visible, hidden = partition_visible(["security", "clean-architecture"], None)
    assert visible == ["security", "clean-architecture"]
    assert hidden == []


def test_partition_with_empty_tuple_hides_everything():
    """() is an explicit "hide everything", distinct from None (no filtering).

    Guards against a truthiness check (`if not visible`) in place of `is None`,
    which would silently turn "hide everything" into "hide nothing".
    """
    visible, hidden = partition_visible(["security", "reliability"], ())
    assert visible == []
    assert hidden == ["security", "reliability"]


def test_saved_file_is_pretty_printed_with_trailing_newline(tmp_path):
    """The literal on-disk text, not just the parsed value.

    The file is committed to the user's repository, so its formatting is part
    of the contract: 2-space indent and a trailing newline keep diffs clean.
    """
    save_visible_standard_ids(tmp_path, ["security"])
    text = (tmp_path / VISIBILITY_RELPATH).read_text(encoding="utf-8")
    assert text == '{\n  "version": 1,\n  "visibleStandardIds": [\n    "security"\n  ]\n}\n'
