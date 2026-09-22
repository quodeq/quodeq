"""tools/migrate_cwe.py must report a non-zero exit code on write failure."""
from __future__ import annotations

import json
import sys

import pytest

# NOTE: migrate_cwe.py matches entries to CWEs via a (principle, file, line)
# key built from the evidence JSONL's "p"/"file"/"line" fields, and only
# records a lookup entry when its "cwe" value is an int (see
# _build_cwe_lookup in tools/migrate_cwe.py). The fixtures below use matching
# principle/file/line values and an integer "cwe" so the lookup is non-empty
# and migrate_file actually reaches the write step.


def _write_fixture(tmp_path):
    eval_dir = tmp_path / "proj" / "evaluation"
    eval_dir.mkdir(parents=True)
    evidence_dir = tmp_path / "proj" / "evidence"
    evidence_dir.mkdir(parents=True)
    eval_path = eval_dir / "security.json"
    eval_path.write_text(
        json.dumps(
            {"violations": [{"principle": "Security", "file": "src/foo.py", "line": 10}]}
        )
    )
    (evidence_dir / "security_evidence.jsonl").write_text(
        json.dumps({"p": "Security", "file": "src/foo.py", "line": 10, "cwe": 79}) + "\n"
    )
    return eval_path


class TestMigrateFileWriteFailure:
    def test_write_failure_returns_error_sentinel(self, tmp_path, monkeypatch) -> None:
        from migrate_cwe import migrate_file
        eval_path = _write_fixture(tmp_path)

        def _boom(*a, **kw):
            raise OSError("disk full")

        monkeypatch.setattr("pathlib.Path.write_text", _boom)

        assert migrate_file(eval_path, apply=True) == (-1, -1)


class TestMainExitCode:
    def test_main_exits_nonzero_when_a_file_write_fails(self, tmp_path, monkeypatch) -> None:
        _write_fixture(tmp_path)
        monkeypatch.setattr("pathlib.Path.write_text", lambda *a, **kw: (_ for _ in ()).throw(OSError("disk full")))
        monkeypatch.setattr(sys, "argv", ["migrate_cwe.py", "--dir", str(tmp_path), "--apply"])
        import migrate_cwe
        with pytest.raises(SystemExit) as exc_info:
            migrate_cwe.main()
        assert exc_info.value.code == 1
