"""Git-side operations for publish_project: clone prep, the staged-diff
commit, push, and the rebase-fallback retry loop.

Split out of shared_publish.py (Task 12). `run_git` is looked up on the
`quodeq.services.shared_publish` facade at call time (via `_run_git`
below), rather than imported directly here, for two reasons: it avoids a
circular import (shared_publish.py imports functions from this module),
and several tests monkeypatch `shared_publish.run_git` to intercept the
push/commit calls this module makes -- a direct top-level import would
bind its own copy and silently escape those patches. `PublishError` is
looked up the same way (deferred, in-function) for the same circular-import
reason.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.services._wiring import (
    PUBLISHED_META_FILENAME,
    check_repo_format,
    ensure_shared_clone,
    refresh_shared_clone,
)


def _run_git(args, *, cwd=None, timeout=300):
    from quodeq.services import shared_publish as _sp

    return _sp.run_git(args, cwd=cwd, timeout=timeout)


def _app_version() -> str:
    from quodeq import __version__

    return __version__ or "0.0.0+dev"


def _prepare_clone(url: str, env: dict | None) -> tuple[Path, str]:
    """Ensure the shared clone exists, is refreshed, and is a format we
    understand. Returns (repo, fmt); does not bootstrap or stage."""
    from quodeq.services.shared_publish import PublishError

    repo = ensure_shared_clone(url, env)
    if repo is None:
        raise PublishError(
            f"could not reach the shared repository, check that git can access {url}"
        )
    refresh_shared_clone(url, env)  # best effort, publish is still guarded by push

    fmt = check_repo_format(repo)
    if fmt == "unsupported_version":
        raise PublishError("this shared repository requires a newer version of quodeq")
    if fmt == "foreign":
        raise PublishError(
            "the configured repository does not look like a quodeq results repository, "
            "refusing to publish into it"
        )
    return repo, fmt


def _commit_staged_changes(repo: Path, project_id: str, count: int) -> None:
    """Commit the staged files, unless the only staged change is a
    republish's fresh published.json (revert that no-op diff first).

    stage_project unconditionally rewrites published.json with a fresh
    publishedAt/publishedBy (needed so those fields DO advance when
    content really changes). That means an otherwise-unchanged republish
    still stages a one-line diff on that file alone once the wall clock
    ticks to a new second. A project's first-ever publish can never hit
    this incorrectly: published.json isn't in HEAD yet, so the staged set
    always includes the new runs/info files alongside it too. If it
    somehow doesn't, the checkout below simply fails against a
    nonexistent HEAD path; that failure is ignored and the normal commit
    path proceeds as if nothing special happened.

    A clean `diff --cached` only means nothing NEW was staged this call;
    it does not mean the remote already has our commits. A prior publish
    can have committed locally and then failed to push (transient network
    error), leaving a local commit the remote never received. Retrying
    with unchanged project files hits this exact "nothing staged" state,
    so callers must still fall through to the push after this returns
    rather than treating it as a no-op.
    """
    from quodeq.services.shared_publish import PublishError

    published_rel = f"evaluations/{project_id}/{PUBLISHED_META_FILENAME}"
    ok_names, names_out = _run_git(["diff", "--cached", "--name-only"], cwd=repo)
    staged_names = [line.strip() for line in names_out.splitlines() if line.strip()]
    if ok_names and staged_names == [published_rel]:
        _run_git(["checkout", "HEAD", "--", published_rel], cwd=repo)

    nothing_staged, _ = _run_git(["diff", "--cached", "--quiet"], cwd=repo)
    if not nothing_staged:
        message = f"Publish {project_id} ({count} runs) via quodeq {_app_version()}"
        ok, out = _run_git(["commit", "-m", message], cwd=repo)
        if not ok:
            raise PublishError(f"git commit failed, {out.strip()[:300]}")


def _push(repo: Path) -> tuple[bool, str]:
    """Push HEAD to the remote's default branch.

    A fresh clone of a brand-new empty bare repo has no commits and no
    origin/HEAD symref yet, so plain ``push origin HEAD`` has nothing
    to compare against. Detect that case and push with an explicit refspec
    instead, deriving the target branch name from the remote's symref (or
    falling back to the local clone's current branch name).
    """
    ok, out = _run_git(["push", "origin", "HEAD"], cwd=repo)
    if ok:
        return ok, out

    # Fall back for a still-unborn remote default branch: push HEAD to an
    # explicit ref name rather than relying on origin/HEAD resolution.
    branch = _remote_default_branch(repo) or _local_branch_name(repo)
    return _run_git(["push", "origin", f"HEAD:refs/heads/{branch}"], cwd=repo)


def _remote_default_branch(repo: Path) -> str | None:
    ok, out = _run_git(["ls-remote", "--symref", "origin", "HEAD"], cwd=repo)
    if not ok:
        return None
    for line in out.splitlines():
        if line.startswith("ref:"):
            # "ref: refs/heads/main\tHEAD"
            ref = line.split()[1]
            if ref.startswith("refs/heads/"):
                return ref[len("refs/heads/") :]
    return None


def _local_branch_name(repo: Path) -> str:
    ok, out = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo)
    name = out.strip()
    return name if ok and name and name != "HEAD" else "main"


def _push_with_rebase_fallback(repo: Path) -> None:
    """Push, retrying once via rebase on a rejected push (a race with
    another publisher), and raise PublishError if both attempts fail."""
    from quodeq.services.shared_publish import PublishError

    ok, out = _push(repo)
    if not ok:
        ok_rebase, out_rebase = _run_git(["pull", "--rebase", "origin", "HEAD"], cwd=repo)
        if ok_rebase:
            ok, out = _push(repo)
        else:
            # A real conflict wedges the persistent clone with a
            # lingering .git/rebase-merge directory, breaking every
            # future publish. The clone is reused across calls, so
            # always leave it clean.
            _run_git(["rebase", "--abort"], cwd=repo)
            out = out_rebase
    if not ok:
        raise PublishError(
            f"push to the shared repository failed, try again. {out.strip()[:300]}"
        )
