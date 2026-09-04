"""Shared-evaluations clone access for delivery layers.

The git-clone-mirror adapter itself lives in ``data/fs/shared_repo.py``; the
API layer does not import ``data/`` directly (see ARCHITECTURE.md import
rules), so the symbols its routes need are re-exported here. Service-layer
code imports ``quodeq.data.fs.shared_repo`` directly.
"""
from __future__ import annotations

from quodeq.data.fs.shared_repo import (  # noqa: F401 — re-exported API
    check_repo_format,
    clone_lock,
    ensure_shared_clone,
    last_synced_at,
    published_meta,
    read_state,
    refresh_shared_clone,
    remove_clone_dir,
    shared_cache_dir,
    shared_evaluations_root,
    shared_index_db_path,
    shared_score_cache_path,
    sync_shared_index,
    validate_remote_url,
)
from quodeq.services.shared_settings import SharedSettings, read_settings, write_settings


def disconnect_shared_repo() -> None:
    """Disconnect the configured shared repository, removing its clone from disk.

    Moved verbatim from the DELETE /api/shared/config route body (Task 20)
    -- the ordering below is load-bearing (see
    test_delete_config_removes_cache_dir and
    test_delete_config_waits_for_clone_lock) and must not be reordered.

    Audit finding A4: disconnecting must not leave the clone's cache dir
    (repo + index.db + score_cache.db, all under shared_cache_dir) behind on
    disk forever. Read the url BEFORE clearing settings (it's gone from
    settings after write_settings), then remove it AFTER -- so a crash
    between the two leaves the (still-usable) clone in place rather than an
    orphaned dir with no settings pointing at it. remove_clone_dir handles
    git's read-only object files (plain rmtree leaves them behind on
    Windows, corrupting a later reconnect's adopted clone) and never
    raises: a half-removed or permission-denied cache dir must not turn a
    disconnect into a 500.

    Review finding: rmtree must run under clone_lock(url), same as every
    other clone mutator (ensure_shared_clone, refresh_shared_clone,
    publish_project) -- otherwise a concurrent publish/refresh holding the
    lock can have its clone directory removed mid-operation, potentially
    leaving a partially-deleted .git that doesn't self-heal.
    """
    settings = read_settings()
    write_settings(SharedSettings(url=None))
    if settings.url is not None:
        with clone_lock(settings.url):
            remove_clone_dir(shared_cache_dir(settings.url))
