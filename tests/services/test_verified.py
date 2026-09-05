from pathlib import Path

from quodeq.services.dismissed import dismissed_keys, dismiss_finding
from quodeq.services.verified import unverify_finding, verified_entries, verify_finding


def test_verify_then_list(tmp_path):
    verify_finding(tmp_path, {"req": "r1", "file": "a.py", "line": 3, "note": "checked the guard"})
    entries = verified_entries(tmp_path)
    assert len(entries) == 1
    e = entries[0]
    assert (e["req"], e["file"], e["line"]) == ("r1", "a.py", 3)
    assert e["note"] == "checked the guard"
    assert e["verifiedAt"]  # ISO timestamp present


def test_unverify_removes_key(tmp_path):
    verify_finding(tmp_path, {"req": "r1", "file": "a.py", "line": 3, "note": "n"})
    unverify_finding(tmp_path, {"req": "r1", "file": "a.py", "line": 3})
    assert verified_entries(tmp_path) == []


def test_verified_and_dismissed_coexist_in_one_log(tmp_path):
    dismiss_finding(tmp_path, {"req": "r2", "file": "b.py", "line": 9, "dismissReason": "fp"})
    verify_finding(tmp_path, {"req": "r1", "file": "a.py", "line": 3, "note": "n"})
    assert dismissed_keys(tmp_path) == {("r2", "b.py", 9)}
    assert [e["req"] for e in verified_entries(tmp_path)] == ["r1"]


def test_verify_without_note_yields_empty_string(tmp_path):
    verify_finding(tmp_path, {"req": "r1", "file": "a.py", "line": 3})
    assert verified_entries(tmp_path)[0]["note"] == ""


def test_reader_skips_unknown_event_types(tmp_path):
    verify_finding(tmp_path, {"req": "r1", "file": "a.py", "line": 3, "note": "n"})
    log = tmp_path / "actions.jsonl"
    log.write_text(
        log.read_text(encoding="utf-8")
        + '{"event_type": "FUTURE_EVENT", "payload": {}}\n',
        encoding="utf-8",
    )
    assert len(verified_entries(tmp_path)) == 1  # unknown line ignored, no crash


def test_verified_entries_with_default_limit_offset(tmp_path):
    """Default call still returns everything up to the max."""
    for i in range(5):
        verify_finding(tmp_path, {"req": f"r{i}", "file": "a.py", "line": i, "note": f"n{i}"})
    entries = verified_entries(tmp_path)
    assert len(entries) == 5


def test_verified_entries_with_explicit_limit_and_offset(tmp_path):
    """Explicit limit/offset slices correctly."""
    for i in range(10):
        verify_finding(tmp_path, {"req": f"r{i}", "file": f"a{i}.py", "line": i, "note": f"n{i}"})

    # Get 3 items starting at offset 2
    entries = verified_entries(tmp_path, offset=2, limit=3)
    assert len(entries) == 3
    # All entries should have their keys present
    assert all("req" in e and "file" in e and "line" in e for e in entries)


def test_verified_entries_out_of_range_offset_returns_empty(tmp_path):
    """Out-of-range offset returns an empty list, not an error."""
    for i in range(5):
        verify_finding(tmp_path, {"req": f"r{i}", "file": "a.py", "line": i})

    entries = verified_entries(tmp_path, offset=100)
    assert entries == []


def test_verified_entries_with_offset_no_limit(tmp_path):
    """Offset without limit returns all remaining entries."""
    for i in range(5):
        verify_finding(tmp_path, {"req": f"r{i}", "file": "a.py", "line": i})

    entries = verified_entries(tmp_path, offset=2)
    assert len(entries) == 3


def test_verified_entries_with_limit_no_offset(tmp_path):
    """Limit without offset returns first N entries."""
    for i in range(10):
        verify_finding(tmp_path, {"req": f"r{i}", "file": "a.py", "line": i})

    entries = verified_entries(tmp_path, limit=5)
    assert len(entries) == 5
