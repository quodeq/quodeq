"""Git-worktree lifecycle for assistant fix sessions.

All git/gh invocations are argv lists (never shell strings) with explicit
-C paths. Output is decoded manually so no text-mode file handles are opened.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

_GIT_TIMEOUT_S = 120
_BRANCH_PREFIX = "quodeq/fix-"
_MAX_BRANCH_TRIES = 5


class WorktreeError(Exception):
    """User-facing worktree/git failure."""


def _run_bytes(argv: list[str], *, cwd: Path | None = None) -> bytes:
    try:
        proc = subprocess.run(  # noqa: S603 - argv list, no shell
            argv, cwd=str(cwd) if cwd else None,
            capture_output=True, timeout=_GIT_TIMEOUT_S, check=False)
    except FileNotFoundError as exc:
        raise WorktreeError(f"{argv[0]} is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise WorktreeError(f"{argv[0]} timed out") from exc
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", errors="replace")
        out = (proc.stdout or b"").decode("utf-8", errors="replace")
        raise WorktreeError((err or out).strip() or f"{argv[0]} failed")
    return proc.stdout or b""


def _run(argv: list[str], *, cwd: Path | None = None) -> str:
    return _run_bytes(argv, cwd=cwd).decode("utf-8", errors="replace")


def diff_text(worktree: Path) -> str:
    """Unified diff of the worktree, including untracked files (intent-to-add).

    Diffs against HEAD, not the index: `git add -N .` records a tracked file's
    deletion in the index, so a plain worktree-vs-index diff would hide it."""
    _run(["git", "-C", str(worktree), "add", "-N", "."])
    return _run(["git", "-C", str(worktree), "diff", "HEAD"])


def diff_stats(worktree: Path) -> list[dict]:
    _run(["git", "-C", str(worktree), "add", "-N", "."])
    out = _run(["git", "-C", str(worktree), "diff", "HEAD", "--numstat"])
    stats = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            added, deleted, name = parts
            stats.append({"file": name,
                          "added": 0 if added == "-" else int(added),
                          "deleted": 0 if deleted == "-" else int(deleted)})
    return stats


def worktrees_base() -> Path:
    return Path(os.environ.get(
        "QUODEQ_WORKTREES_DIR", str(Path.home() / ".quodeq" / "worktrees")))


def _safe_segment(value: str) -> str:
    """Collapse a user-facing name to a filesystem-safe single path segment."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value or "").strip("-.")
    return cleaned or "project"


@dataclass
class WorktreeManager:
    repo_root: Path
    path: Path
    branch: str

    @classmethod
    def for_session(cls, repo_root: Path, project_id: str, session_id: str,
                    base: Path | None = None) -> "WorktreeManager":
        base = base or worktrees_base()
        short = session_id[:8]
        return cls(repo_root=Path(repo_root),
                   path=base / _safe_segment(project_id or "project") / short,
                   branch=f"{_BRANCH_PREFIX}{short}")

    def exists(self) -> bool:
        return self.path.is_dir() and (self.path / ".git").exists()

    def create(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "-C", str(self.repo_root), "worktree", "prune"])
        if self.path.exists() and not self.exists():
            # stale leftover directory (crash, stray files); a live worktree has .git
            shutil.rmtree(self.path, ignore_errors=True)
        last_err: WorktreeError | None = None
        for attempt in range(_MAX_BRANCH_TRIES):
            candidate = (self.branch if attempt == 0
                         else f"{self.branch}-{attempt + 1}")
            try:
                _run(["git", "-C", str(self.repo_root), "worktree", "add",
                      "-b", candidate, str(self.path)])
                self.branch = candidate
                return
            except WorktreeError as exc:
                last_err = exc
                if "a branch named" not in str(exc):
                    raise
        raise WorktreeError(f"could not allocate a fix branch: {last_err}")

    def diff(self) -> str:
        return diff_text(self.path)

    def remove(self, delete_branch: bool = True) -> None:
        if self.exists():
            _run(["git", "-C", str(self.repo_root), "worktree", "remove",
                  "--force", str(self.path)])
        else:
            shutil.rmtree(self.path, ignore_errors=True)
            _run(["git", "-C", str(self.repo_root), "worktree", "prune"])
        if delete_branch:
            try:
                _run(["git", "-C", str(self.repo_root), "branch", "-D", self.branch])
            except WorktreeError:
                pass  # branch already gone; removal is best-effort

    def apply_to_repo(self) -> list[dict]:
        """Apply the worktree diff onto the user's working tree, uncommitted.

        git apply --check runs first so a conflict applies NOTHING. The patch
        is generated against HEAD with --binary and written as raw bytes so
        deletions, binary and non-UTF-8 changes survive the roundtrip. The
        patch file lives OUTSIDE the worktree so a failed cleanup can never
        leak it into a later diff or apply."""
        _run(["git", "-C", str(self.path), "add", "-N", "."])
        patch = _run_bytes(["git", "-C", str(self.path), "diff", "HEAD",
                            "--binary"])
        if not patch.strip():
            raise WorktreeError("no changes to apply")
        stats = diff_stats(self.path)
        fd, patch_name = tempfile.mkstemp(prefix="quodeq-apply-",
                                          suffix=".patch")
        patch_file = Path(patch_name)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(patch)
            _run(["git", "-C", str(self.repo_root), "apply", "--check",
                  str(patch_file)])
            _run(["git", "-C", str(self.repo_root), "apply", str(patch_file)])
        finally:
            patch_file.unlink(missing_ok=True)
        return stats

    def commit_all(self, message: str) -> None:
        status = _run(["git", "-C", str(self.path), "status", "--porcelain"])
        if not status.strip():
            return
        _run(["git", "-C", str(self.path), "add", "-A"])
        _run(["git", "-C", str(self.path),
              "-c", "user.name=Quodeq Assistant",
              "-c", "user.email=assistant@quodeq.local",
              "commit", "-q", "-m", message])

    def create_pr(self, title: str, body: str) -> dict:
        """Commit, push, gh pr create. Fail-soft: the branch is always kept."""
        self.commit_all(title or "Quodeq assistant fix")
        try:
            _run(["git", "-C", str(self.path), "push", "-u", "origin", self.branch])
        except WorktreeError as exc:
            return {"prUrl": None, "branch": self.branch, "pushed": False,
                    "message": (f"Push failed: {exc}. The branch exists locally,"
                                " push it and open a PR manually.")}
        if shutil.which("gh") is None:
            return {"prUrl": None, "branch": self.branch, "pushed": True,
                    "message": ("Branch pushed. Install and authenticate the gh"
                                " CLI, or open the PR from your git host.")}
        # gh runs with the parent process env on purpose (it needs the user's
        # own auth). It is NOT routed through the scrubbed-env CLI spawner
        # used for AI provider CLIs; that scrubber exists to keep secrets
        # away from a model-driven process, and `gh pr create` here is a
        # human-approved, fixed-argv action.
        try:
            out = _run(["gh", "pr", "create", "--title", title or self.branch,
                        "--body", body or "", "--head", self.branch],
                       cwd=self.path)
        except WorktreeError as exc:
            return {"prUrl": None, "branch": self.branch, "pushed": True,
                    "message": f"gh pr create failed: {exc}"}
        url = out.strip().splitlines()[-1] if out.strip() else None
        return {"prUrl": url, "branch": self.branch, "pushed": True,
                "message": "PR created"}


def ensure_session_worktree(repository, *, repo_root: Path, project_id: str | None,
                            session_id: str, base: Path | None = None) -> WorktreeManager:
    """Return the session's active worktree, creating one when needed."""
    row = repository.get_worktree(session_id)
    if row and row["status"] == "active" and Path(row["path"]).is_dir():
        return WorktreeManager(repo_root=Path(row["repo_root"]),
                               path=Path(row["path"]), branch=row["branch"])
    manager = WorktreeManager.for_session(repo_root, project_id or "project",
                                          session_id, base=base)
    if manager.path.exists():  # crash leftover or terminal reuse: start clean
        shutil.rmtree(manager.path, ignore_errors=True)
        _run(["git", "-C", str(repo_root), "worktree", "prune"])
    manager.create()
    repository.upsert_worktree(session_id=session_id, project_id=project_id,
                               repo_root=str(repo_root), path=str(manager.path),
                               branch=manager.branch)
    return manager


def gc_stale_worktrees(repository) -> None:
    """Mark active rows whose worktree directory vanished (crash cleanup)."""
    for row in repository.list_worktrees("active"):
        if not Path(row["path"]).is_dir():
            repository.set_worktree_status(row["session_id"], "stale")
