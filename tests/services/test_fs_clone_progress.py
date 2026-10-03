import importlib

import pytest

from quodeq.shared.git_errors import GitFailureKind

_fs_clone = importlib.import_module("quodeq.services._fs_clone")
CloneError, run_git_clone = _fs_clone.CloneError, _fs_clone.run_git_clone


def test_run_git_clone_with_progress_reports_percent_and_bytes(monkeypatch, tmp_path):
    updates = []

    def fake_streaming(self, url, dest, extra_args, *, timeout_s, git_config=(), on_line):
        on_line("Receiving objects:  45% (1200/2650), 12.3 MiB | 2.1 MiB/s")
        return True, ""

    monkeypatch.setattr("quodeq.data.fs.repo_clone.GitCloneClient.clone_streaming", fake_streaming)
    monkeypatch.setattr("quodeq.services._fs_clone._pinned_git_config", lambda url: [])
    run_git_clone("https://github.com/o/r.git", tmp_path / "r", timeout_s=5, progress=updates.append)
    assert updates and updates[0].percent == 45 and updates[0].bytes == int(12.3 * 1024 * 1024)


def test_run_git_clone_with_progress_maps_failure_tail_to_clone_error(monkeypatch, tmp_path):
    def fake_streaming(self, url, dest, extra_args, *, timeout_s, git_config=(), on_line):
        return False, "remote: Repository not found.\nfatal: repository 'https://github.com/o/r.git/' not found"

    monkeypatch.setattr("quodeq.data.fs.repo_clone.GitCloneClient.clone_streaming", fake_streaming)
    monkeypatch.setattr("quodeq.services._fs_clone._pinned_git_config", lambda url: [])
    with pytest.raises(CloneError) as exc:
        run_git_clone("https://github.com/o/r.git", tmp_path / "r", timeout_s=5, progress=lambda _u: None)
    assert exc.value.kind is GitFailureKind.NOT_FOUND
