from quodeq.data.fs.repo_clone import GitCloneClient


def test_clone_streaming_feeds_every_stderr_line_and_returns_ok(monkeypatch, tmp_path):
    seen = []

    def fake_streaming(args, *, cwd=None, timeout, env=None, on_line):
        # run_git_streaming prepends the git binary itself, so args start after it.
        assert "clone" in args and "--progress" in args and "--" in args
        on_line("Receiving objects:  45% (1200/2650), 12.3 MiB | 2.1 MiB/s")
        on_line("Resolving deltas: 100% (10/10), done.")
        return True, "Resolving deltas: 100% (10/10), done."

    monkeypatch.setattr("quodeq.data.fs.repo_clone.run_git_streaming", fake_streaming)
    ok, tail = GitCloneClient().clone_streaming(
        "https://github.com/o/r.git", tmp_path / "r", [], timeout_s=5, on_line=seen.append)
    assert ok and len(seen) == 2 and "Resolving" in tail


def test_clone_streaming_passes_env_and_closes_stdin(monkeypatch, tmp_path):
    captured = {}

    def fake_streaming(args, *, cwd=None, timeout, env=None, on_line):
        captured["env"] = env
        captured["timeout"] = timeout
        return False, "fatal: repository not found"

    monkeypatch.setattr("quodeq.data.fs.repo_clone.run_git_streaming", fake_streaming)
    ok, tail = GitCloneClient({"GIT_ASKPASS": "x"}).clone_streaming(
        "https://github.com/o/r.git", tmp_path / "r", [], timeout_s=7, on_line=lambda _l: None)
    assert ok is False and "not found" in tail
    assert captured["timeout"] == 7 and captured["env"]["GIT_ASKPASS"] == "x"
