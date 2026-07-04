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


def test_reader_skips_unknown_event_types(tmp_path):
    verify_finding(tmp_path, {"req": "r1", "file": "a.py", "line": 3, "note": "n"})
    log = tmp_path / "actions.jsonl"
    log.write_text(
        log.read_text(encoding="utf-8")
        + '{"event_type": "FUTURE_EVENT", "payload": {}}\n',
        encoding="utf-8",
    )
    assert len(verified_entries(tmp_path)) == 1  # unknown line ignored, no crash
