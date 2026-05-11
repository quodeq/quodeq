"""Walk a project, parse files, populate the symbol index."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import quodeq.resolver.languages  # noqa: F401  self-register adapters
from quodeq.resolver.cache import IndexCache
from quodeq.resolver.registry import LanguageNotSupported, get_adapter_for

_SKIP_DIRS = frozenset({".git", "__pycache__", "node_modules", ".venv", "dist", "build"})


def build_index(cache: IndexCache, project_root: Path) -> int:
    """Walk project_root, parse every supported file, populate the cache.

    Returns the number of files indexed.
    """
    project_root = project_root.resolve()
    count = 0
    for path in _iter_source_files(project_root):
        rel = str(path.relative_to(project_root))
        try:
            adapter = get_adapter_for(path)
        except LanguageNotSupported:
            continue

        source = path.read_bytes()
        sha = hashlib.sha256(source).hexdigest()
        result = adapter.parse(source)

        _insert_file_records(cache, rel, sha, adapter.language, result)
        count += 1

    cache.conn.commit()
    return count


def _iter_source_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.relative_to(root).parts):
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
