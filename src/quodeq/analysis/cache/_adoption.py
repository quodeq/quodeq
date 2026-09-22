"""Adopt a cached result across a file move.

A classify miss with a real content hash asks the backend's content index
for entries written with the same (content hash, dimension, params hash).
If one of them is the same file under another path (same basename, same
``path_role``), its findings are cloned under the new key with the ``file``
field rewritten, and the clone is returned as the hit. Provenance records
``adopted_from`` so the reuse is visible in the cache log line and never
silent.

Why these guards: the bytes are identical, so path-insensitive judgments
carry over exactly. Clean-architecture and the test/production downweight do
read the path, which is why a rename (different basename) or a role change
re-evaluates instead. Adoption is deliberately cross-project: entries carry
no project identity and the cache is already cost-first across model and
standards changes.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import PurePosixPath

from quodeq.analysis.cache.backend import CacheBackend
from quodeq.analysis.cache.entry import CacheEntry
from quodeq.analysis.cache.key import CacheKey
from quodeq.context.path_role import path_role


def _compatible_move(old_path: str, new_path: str) -> bool:
    if old_path == new_path:
        return False
    if PurePosixPath(old_path).name != PurePosixPath(new_path).name:
        return False
    return path_role(old_path) == path_role(new_path)


def _clone_for(src: CacheEntry, *, new_key: str, new_path: str, language: str) -> CacheEntry:
    findings = [
        {**f, "file": new_path} if f.get("file") == src.file_path else dict(f)
        for f in src.findings
    ]
    provenance = {**(src.provenance or {}), "adopted_from": src.file_path}
    return replace(
        src, key=new_key, file_path=new_path, findings=findings, language=language,
        provenance=provenance,
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def try_adopt(
    cache: CacheBackend, struct: CacheKey, new_key: str, *, language: str,
) -> CacheEntry | None:
    """Return an adopted entry for *struct* written under *new_key*, or None.

    None when the backend has no content index, the content hash is blank,
    or no indexed entry passes the move guards and verification.
    """
    finder = getattr(cache, "find_by_content", None)
    if finder is None or not struct.file_content_hash:
        return None
    for row in finder(struct.file_content_hash, struct.dimension, struct.params_hash):
        if not _compatible_move(row.file_path, struct.file_path):
            continue
        src = cache.get(row.key)
        if (
            src is None
            or src.file_content_hash != struct.file_content_hash
            or src.dimension != struct.dimension
        ):
            continue
        adopted = _clone_for(src, new_key=new_key, new_path=struct.file_path, language=language)
        cache.put(new_key, adopted)
        return adopted
    return None
