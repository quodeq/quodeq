import importlib

import pytest

from quodeq.data.fs import git_stream
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


def _stub_clone_env(monkeypatch, results):
    calls = []

    def fake_streaming(self, url, dest, extra_args, *, timeout_s, git_config=(), on_line):
        calls.append(list(extra_args))
        return results(calls, on_line)

    monkeypatch.setattr("quodeq.services._fs_clone._pinned_git_config", lambda url: [])
    monkeypatch.setattr("quodeq.services._fs_clone.remove_clone_dir", lambda dest: None)
    monkeypatch.setattr("quodeq.data.fs.repo_clone.GitCloneClient.clone_streaming", fake_streaming)
    return calls


@pytest.mark.parametrize(("tail", "kind"), [
    (git_stream.GIT_MISSING, GitFailureKind.GIT_MISSING),
    (git_stream.TIMED_OUT, GitFailureKind.TIMEOUT),
    (git_stream.FAILED_TO_RUN, GitFailureKind.UNKNOWN),
    ("No space left on device", GitFailureKind.DISK),
])
def test_runner_failure_tails_map_to_the_buffered_kinds_and_never_retry(monkeypatch, tmp_path, tail, kind):
    calls = _stub_clone_env(monkeypatch, lambda _calls, _on_line: (False, tail))
    with pytest.raises(CloneError) as exc:
        run_git_clone("https://github.com/o/r.git", tmp_path / "r", timeout_s=5, shallow_months=6, progress=lambda _u: None)
    assert exc.value.kind is kind and exc.value.retryable is False and len(calls) == 1


def test_shallow_failure_falls_back_to_full_clone_and_both_attempts_report_progress(monkeypatch, tmp_path):
    updates = []

    def results(calls, on_line):
        if len(calls) == 1:
            on_line("Receiving objects:  10% (1/10), 1.0 MiB | 1.0 MiB/s")
            return False, "fatal: error processing shallow info: 4"
        on_line("Receiving objects:  90% (9/10), 9.0 MiB | 1.0 MiB/s")
        return True, ""

    calls = _stub_clone_env(monkeypatch, results)
    run_git_clone("https://github.com/o/r.git", tmp_path / "r", timeout_s=5, shallow_months=6, progress=updates.append)
    assert len(calls) == 2
    assert any(a.startswith("--shallow-since=") for a in calls[0]) and calls[1] == []
    assert [u.percent for u in updates] == [10, 90]
