"""Origin/publish helpers for tests/data/test_shared_repo*.py siblings."""
import json
import subprocess
from pathlib import Path

from quodeq.data.fs.shared_repo import ensure_shared_clone, shared_repo_path


def _make_origin(tmp_path: Path) -> str:
    """Create a bare repo with one commit; return its file:// URL."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    work = tmp_path / "seed"
    subprocess.run(["git", "clone", str(origin), str(work)], check=True, capture_output=True)
    (work / "hello.txt").write_text("hi", encoding="utf-8")
    for cmd in (
        ["git", "add", "."],
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "seed"],
        ["git", "push", "origin", "HEAD"],
    ):
        subprocess.run(cmd, cwd=work, check=True, capture_output=True)
    return f"file://{origin}"


def _publish_project_as(
    monkeypatch, url: str, root: Path, project_id: str, author: str
) -> None:
    """Publish project_id into the shared repo at url, attributed to author.

    Pre-clones (if needed) and pins the clone's LOCAL git config user.name to
    author before publishing, so published.json's publishedBy (sourced from
    `git config user.name`, not GIT_AUTHOR_NAME/GIT_COMMITTER_NAME) is
    deterministic. Also sets GIT_AUTHOR_NAME/EMAIL and GIT_COMMITTER_NAME/EMAIL
    (via monkeypatch, so they don't leak into other tests) so the underlying
    `git commit` succeeds without needing any git identity configured on the
    machine running the tests.
    """
    from quodeq.services.shared_publish import publish_project

    monkeypatch.setenv("GIT_AUTHOR_NAME", author)
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", f"{author}@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", author)
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", f"{author}@example.com")

    assert ensure_shared_clone(url) is not None
    subprocess.run(
        ["git", "config", "user.name", author], cwd=shared_repo_path(url), check=True, capture_output=True,
    )
    publish_project(project_id, url, evaluations_root=root)


def _make_minimal_project(root: Path, project_id: str) -> None:
    project = root / project_id
    run = project / "run-1"
    (run / "evidence").mkdir(parents=True)
    (project / "repository_info.json").write_text('{"name":"demo"}')
    (run / "status.json").write_text(json.dumps({"state": "done", "schema_version": 2}))
    (run / "dimensions.json").write_text("{}")
    (run / "events.jsonl").write_text("{}\n")


def _fake_git_log(calls: list[list[str]], *, fail_call: int | None = None):
    """run_git stand-in: one commit per pathspec, authored after its dir name.
    Call number *fail_call* (1-based) reports failure instead."""

    def _run(args, **kwargs):
        calls.append(args)
        if fail_call is not None and len(calls) == fail_call:
            return False, ""
        names = [p.removeprefix("evaluations/") for p in args[args.index("--") + 1:]]
        out = "".join(
            f"\x1f{n}-author|{i}\x00\nevaluations/{n}/status.json\x00"
            for i, n in enumerate(names, 1)
        )
        return True, out

    return _run
