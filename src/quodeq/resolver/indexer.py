"""Walk a project, parse files, populate the symbol index."""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import quodeq.resolver.languages  # noqa: F401  self-register adapters
from quodeq.resolver.cache import IndexCache
from quodeq.resolver.registry import LanguageNotSupported, get_adapter_for

# Explicit non-dotted directories to skip. Dotted directories (`.git`, `.venv`,
# `.mypy_cache`, `.claude`, `.worktrees`, ...) are blanket-skipped by the
# leading-dot rule in `_iter_source_files`. Listing them here would be
# redundant.
_SKIP_DIRS = frozenset({
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "target",      # Cargo, sbt
    "out",         # generic build output
    "htmlcov",     # coverage HTML
    "coverage",    # coverage reports
    "site-packages",
})

logger = logging.getLogger("quodeq.resolver.indexer")


def build_index(cache: IndexCache, project_root: Path) -> dict:
    """Walk project_root, parse new/changed files, populate the cache.

    Returns a summary dict: {"parsed": N, "skipped": M, "removed": K, "elapsed_s": T}.
    Files unchanged since the previous index (matching sha256 + parser_version) are
    skipped entirely. Files removed from disk since last index have their rows deleted.
    """
    project_root = project_root.resolve()
    start = time.monotonic()

    # Load existing hashes keyed by relative path
    existing_hashes = _load_existing_hashes(cache)

    # Check parser_version compatibility. If the version changed since the last
    # index, the existing hashes are invalid (different grammar might produce a
    # different parse). Force a full rebuild in that case.
    recorded_parser_version = cache.get_meta("parser_version")
    current_parser_version = cache.get_meta("parser_version")
    parser_changed = (
        recorded_parser_version is not None
        and existing_hashes
        and recorded_parser_version != current_parser_version
    )
    if parser_changed:
        logger.info(
            "Parser version changed (%s != %s); forcing full re-index",
            recorded_parser_version,
            current_parser_version,
        )
        existing_hashes = {}

    parsed = 0
    skipped = 0
    seen_rels: set[str] = set()
    total_supported = 0

    for path in _iter_source_files(project_root):
        rel = str(path.relative_to(project_root))
        try:
            adapter = get_adapter_for(path)
        except LanguageNotSupported:
            continue
        total_supported += 1
        seen_rels.add(rel)

        source = path.read_bytes()
        sha = hashlib.sha256(source).hexdigest()

        if existing_hashes.get(rel) == sha:
            skipped += 1
            if (parsed + skipped) % 200 == 0:
                logger.info(
                    "Indexing %s/%s files (parsed=%d, skipped=%d)",
                    parsed + skipped,
                    total_supported,
                    parsed,
                    skipped,
                )
            continue

        result = adapter.parse(source)
        _insert_file_records(cache, rel, sha, adapter.language, result)
        parsed += 1
        if (parsed + skipped) % 200 == 0:
            logger.info(
                "Indexing %s files (parsed=%d, skipped=%d)",
                parsed + skipped,
                parsed,
                skipped,
            )

    # Remove rows for files that disappeared from disk since the last index
    removed = 0
    for rel in list(existing_hashes.keys()):
        if rel in seen_rels:
            continue
        _delete_file_records(cache, rel)
        removed += 1

    cache.conn.commit()
    elapsed = time.monotonic() - start
    summary = {
        "parsed": parsed,
        "skipped": skipped,
        "removed": removed,
        "elapsed_s": round(elapsed, 2),
    }
    logger.info(
        "build_index complete: %s files parsed, %s skipped, %s removed in %.2fs",
        parsed,
        skipped,
        removed,
        elapsed,
    )
    return summary


def _load_existing_hashes(cache: IndexCache) -> dict[str, str]:
    rows = cache.execute("SELECT file, sha256 FROM file_hashes")
    return {row["file"]: row["sha256"] for row in rows}


def _delete_file_records(cache: IndexCache, file: str) -> None:
    """Remove all rows for a file that no longer exists."""
    for table in ("classes", "functions", "function_params", "imports", "call_sites", "file_hashes"):
        cache.conn.execute(f"DELETE FROM {table} WHERE file=?", (file,))


def _iter_source_files(root: Path):
    """Yield candidate source files under `root`, skipping common noise dirs.

    Skips any path that contains a directory component which (a) starts with
    `.` (catches caches and tool dirs like `.git`, `.venv`, `.mypy_cache`,
    `.claude`, `.worktrees`, `.tox`, `.idea`, `.vscode`, ...) or (b) is in
    the explicit `_SKIP_DIRS` set (for non-dotted noise like `node_modules`,
    `build`, `target`).
    """
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        parts = path.relative_to(root).parts
        if any(p.startswith(".") or p in _SKIP_DIRS for p in parts[:-1]):
            continue
        yield path


def _insert_file_records(
    cache: IndexCache,
    file: str,
    sha: str,
    language: str,
    result,
) -> None:
    cur = cache.conn
    cur.execute("DELETE FROM classes WHERE file=?", (file,))
    cur.execute("DELETE FROM functions WHERE file=?", (file,))
    cur.execute("DELETE FROM function_params WHERE file=?", (file,))
    cur.execute("DELETE FROM imports WHERE file=?", (file,))
    cur.execute("DELETE FROM call_sites WHERE file=?", (file,))
    cur.execute("DELETE FROM file_hashes WHERE file=?", (file,))

    cur.execute(
        "INSERT INTO file_hashes(file, sha256, language, indexed_at) VALUES (?, ?, ?, ?)",
        (file, sha, language, datetime.now(timezone.utc).isoformat()),
    )

    for c in result.classes:
        cur.execute(
            "INSERT INTO classes(file, line, name, base_list, language) VALUES (?, ?, ?, ?, ?)",
            (file, c.line, c.name, ",".join(c.bases), language),
        )
    for fn in result.functions:
        cur.execute(
            "INSERT INTO functions(file, line, name, signature, return_type, language) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (file, fn.line, fn.name, fn.signature, fn.return_type, language),
        )
    for p in result.params:
        cur.execute(
            "INSERT INTO function_params(file, function_line, function_name, param_name, "
            "annotation_text, annotation_names, language) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                file,
                p.function_line,
                p.function_name,
                p.param_name,
                p.annotation_text,
                ",".join(p.annotation_names),
                language,
            ),
        )
    for i in result.imports:
        cur.execute(
            "INSERT INTO imports(file, line, imported_name, source_module, is_lazy, language) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (file, i.line, i.imported_name, i.source_module, 1 if i.is_lazy else 0, language),
        )
    for c in result.calls:
        cur.execute(
            "INSERT INTO call_sites(file, line, callee, language) VALUES (?, ?, ?, ?)",
            (file, c.line, c.callee, language),
        )
