"""Shared-evaluations clone access for delivery layers.

The git-clone-mirror adapter itself lives in ``data/fs/shared_repo.py``; the
API layer does not import ``data/`` directly (see ARCHITECTURE.md import
rules), so the symbols its routes need are re-exported here. Service-layer
code imports ``quodeq.data.fs.shared_repo`` directly.
"""
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
