"""CI surfaces exclude dismissed/deleted findings."""
import json

from quodeq.ci._suppressions import filter_suppressed_violations
from quodeq.services.dismissed import dismiss_finding


def test_dismissed_violation_dropped(tmp_path):
    # Use the real dismiss path (ActionLogWriter under the hood) rather than
    # hand-writing actions.jsonl: a hand-rolled event_id must be a valid UUID
    # or read_action_events silently skips the line as malformed.
    dismiss_finding(tmp_path, {"req": "R-1", "file": "a.kt", "line": 10})
    report = {"dimension": "maintainability", "violations": [
        {"req": "R-1", "file": "a.kt", "line": 10, "practiceId": "Modularity"},
        {"req": "R-2", "file": "b.kt", "line": 2, "practiceId": "Modularity"},
    ]}
    out = filter_suppressed_violations(report, tmp_path)
    assert [v["req"] for v in out["violations"]] == ["R-2"]


def test_deleted_principle_file_dropped(tmp_path):
    (tmp_path / "deleted.json").write_text(json.dumps([
        {"dimension": "maintainability", "principle": "Modularity",
         "file": "a.kt", "deleted_at": "2026-07-24T10:00:00Z"},
    ]))
    report = {"dimension": "maintainability", "violations": [
        {"req": "R-1", "file": "a.kt", "line": 10, "practiceId": "Modularity"},
        {"req": "R-2", "file": "b.kt", "line": 2, "practiceId": "Modularity"},
    ]}
    out = filter_suppressed_violations(report, tmp_path)
    assert [v["req"] for v in out["violations"]] == ["R-2"]


def test_no_suppressions_is_identity(tmp_path):
    report = {"dimension": "maintainability",
              "violations": [{"req": "R-1", "file": "a.kt", "line": 10,
                              "practiceId": "Modularity"}]}
    assert filter_suppressed_violations(report, tmp_path) == report
