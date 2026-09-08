"""Shared-repo format/bootstrap, index sync, and publish attribution.

Split from ``shared_repo.py`` to keep that file under the size ratchet's
300-line cap. Moved verbatim; re-exported from ``shared_repo.py`` (and, in
turn, from ``services/shared_repo.py``) so existing import sites are
unaffected.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.data.fs.shared_repo import run_git, shared_cache_dir, shared_evaluations_root, shared_repo_path

MARKER_FILENAME = "quodeq.json"
FORMAT_NAME = "quodeq-shared-evaluations"
FORMAT_VERSION = 1
PUBLISHED_META_FILENAME = "published.json"

_GITIGNORE_CONTENT = "**/evaluation.db\n*.log\n"


def check_repo_format(repo_root: Path) -> str:
    marker = repo_root / MARKER_FILENAME
    if marker.exists():
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return "foreign"

        # Marker JSON must be a dict; if not, it's foreign.
        if not isinstance(data, dict):
            return "foreign"

        if data.get("format") != FORMAT_NAME:
            return "foreign"

        # Try to parse version as int; if it fails or is non-numeric, unsupported.
        try:
            version = int(data.get("version", 0))
        except (ValueError, TypeError):
            return "unsupported_version"

        if version > FORMAT_VERSION:
            return "unsupported_version"
        return "ok"

    try:
        entries = [p for p in repo_root.iterdir() if p.name != ".git"]
    except OSError:
        return "foreign"
    return "empty" if not entries else "foreign"


def bootstrap_repo_layout(repo_root: Path) -> None:
    marker_content = json.dumps({"format": FORMAT_NAME, "version": FORMAT_VERSION}) + "\n"
    (repo_root / MARKER_FILENAME).write_text(marker_content, encoding="utf-8")
    (repo_root / ".gitignore").write_text(_GITIGNORE_CONTENT, encoding="utf-8")
    evaluations = repo_root / "evaluations"
    evaluations.mkdir(exist_ok=True)
    (evaluations / ".gitkeep").write_text("", encoding="utf-8")


def shared_index_db_path(url: str, env: dict | None = None) -> Path:
    return shared_cache_dir(url, env) / "index.db"


def shared_score_cache_path(url: str, env: dict | None = None) -> Path:
    return shared_cache_dir(url, env) / "score_cache.db"


def sync_shared_index(url: str, env: dict | None = None) -> None:
    from quodeq.data.sqlite.run_index import open_index, sync_index

    root = shared_evaluations_root(url, env)
    if not root.is_dir():
        return
    db = open_index(shared_index_db_path(url, env))
    try:
        sync_index(db, root)
    finally:
        db.close()


def read_state(url: str, env: dict | None = None) -> str:
    """State of the local shared clone: ok | empty | foreign |
    unsupported_version | missing. "empty" (cloned, never published into)
    is servable -- routes return an empty listing for it."""
    repo = shared_repo_path(url, env)
    if not (repo / ".git").exists():
        return "missing"
    return check_repo_format(repo)


def _read_published_json(entry: Path) -> dict | None:
    """Read <entry>/published.json, validating both keys.

    Returns None on any failure (missing file, bad JSON, wrong shape) so the
    caller can fall back to the git-log-derived legacy path -- never raises.
    """
    try:
        data = json.loads((entry / PUBLISHED_META_FILENAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    by = data.get("publishedBy")
    at = data.get("publishedAt")
    if not isinstance(by, str) or not by:
        return None
    if not isinstance(at, int) or isinstance(at, bool):
        return None
    return {"publishedBy": by, "publishedAt": at}


def _legacy_git_attribution(repo: Path, names: list[str]) -> dict[str, dict]:
    """Author and commit time of the newest commit touching each
    ``evaluations/<name>``, from one ``git log`` walk over all *names*.

    Commits come newest first, so the first one listing a file under a dir
    is the commit ``git log -1 -- evaluations/<name>`` would report, without
    a subprocess per dir. ``-z`` keeps paths unquoted and NUL-terminated so
    a non-ASCII dir name still matches ``entry.name``. Merge commits list no
    files and so never win; that only differs from ``-1`` on a merge that
    itself changed a project dir, which the shared clone's linear history
    (commit + push, fetch + reset) does not produce.
    """
    if not names:
        return {}
    ok, out = run_git(
        ["log", "-z", "--format=%x1f%an|%ct", "--name-only", "--", *(f"evaluations/{n}" for n in names)],
        cwd=repo,
    )
    if not ok:
        return {}
    wanted = set(names)
    result: dict[str, dict] = {}
    meta: dict | None = None
    for token in out.split("\x00"):
        if token.startswith("\x1f"):
            author, _, ts = token[1:].rpartition("|")
            try:
                meta = {"publishedBy": author, "publishedAt": int(ts)}
            except ValueError:
                meta = None
            continue
        parts = token.lstrip("\n").split("/", 2)
        if meta is None or len(parts) < 2 or parts[0] != "evaluations":
            continue
        if parts[1] in wanted and parts[1] not in result:
            result[parts[1]] = meta
    return result


def published_meta(url: str, env: dict | None = None) -> dict[str, dict]:
    """Attribution per published project: who published it, and when.

    Prefers the published.json written by stage_project at publish time
    (see shared_publish.py). Falls back to the legacy git-log-derived
    lookup, batched into one git call for every project dir published
    before that file existed. The fallback is only correct because the
    clone is full history (no --depth) -- a shallow clone made `git log -1
    -- path` return the tip commit for every path, misattributing every
    project except the most recently pushed one (audit finding C1).
    """
    repo = shared_repo_path(url, env)
    root = shared_evaluations_root(url, env)
    result: dict[str, dict] = {}
    if not root.is_dir():
        return result
    legacy: list[str] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        meta = _read_published_json(entry)
        if meta is not None:
            result[entry.name] = meta
        else:
            legacy.append(entry.name)
    result.update(_legacy_git_attribution(repo, legacy))
    return result
