"""WorktreeManager: create/apply/commit/PR lifecycle for one session's git
worktree.

Split from ``worktree.py`` to keep that file under the size ratchet's
300-line cap. Moved verbatim; the low-level git helpers (``_run``,
``_run_bytes``, ``WorktreeError``, ``diff_text``, ``diff_stats``,
``worktrees_base``) stay imported from ``worktree.py`` rather than
duplicated.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from quodeq.assistant.worktree import (
    WorktreeError, _run, _run_bytes, diff_stats, diff_text, worktrees_base,
)

_BRANCH_PREFIX = "quodeq/fix-"
_MAX_BRANCH_TRIES = 5


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

    def commit_all(self, message: str) -> bool:
        status = _run(["git", "-C", str(self.path), "status", "--porcelain"])
        if not status.strip():
            return False
        _run(["git", "-C", str(self.path), "add", "-A"])
        _run(["git", "-C", str(self.path),
              "-c", "user.name=Quodeq Assistant",
              "-c", "user.email=assistant@quodeq.local",
              "commit", "-q", "-m", message])
        return True

    def create_pr(self, title: str, body: str) -> dict:
        """Commit, push, gh pr create. Fail-soft: the branch is always kept.

        On push failure the just-made commit is rolled back (soft) so the
        changes return to the working tree and in-app apply/diff/review keep
        working; on push success the commit stays (it is on the remote)."""
        committed = self.commit_all(title or "Quodeq assistant fix")
        try:
            _run(["git", "-C", str(self.path), "push", "-u", "origin", self.branch])
        except WorktreeError as exc:
            if committed:
                _run(["git", "-C", str(self.path), "reset", "--soft", "HEAD~1"])
            return {"prUrl": None, "branch": self.branch, "pushed": False,
                    "message": (f"Push failed: {exc}. The changes are back in the"
                                " worktree; apply them or open a PR manually.")}
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
