"""Cross-file resolver queries backed by the SQLite symbol index."""

from __future__ import annotations

from quodeq.resolver.cache import IndexCache
from quodeq.resolver.models import Location


def where_defined(cache: IndexCache, name: str, kind: str = "class") -> Location | None:
    """Find the first definition matching `name`.

    kind is one of: "class", "function". Returns None if not found.
    """
    table = {"class": "classes", "function": "functions"}[kind]
    row = cache.conn.execute(
        f"SELECT file, line FROM {table} WHERE name = ? ORDER BY file, line LIMIT 1",
        (name,),
    ).fetchone()
    if not row:
        return None
    return Location(file=row["file"], line=row["line"])


def subclasses_of(cache: IndexCache, name: str) -> list[Location]:
    """Find every class whose base_list contains the given name."""
    rows = cache.conn.execute(
        "SELECT file, line FROM classes "
        "WHERE ',' || base_list || ',' LIKE '%,' || ? || ',%' "
        "ORDER BY file, line",
        (name,),
    ).fetchall()
    return [Location(file=r["file"], line=r["line"]) for r in rows]


def param_type_users(cache: IndexCache, type_name: str) -> list[Location]:
    """Find function definitions with a parameter annotated using `type_name`."""
    rows = cache.conn.execute(
        "SELECT file, function_line AS line FROM function_params "
        "WHERE ',' || annotation_names || ',' LIKE '%,' || ? || ',%' "
        "ORDER BY file, function_line",
        (type_name,),
    ).fetchall()
    return [Location(file=r["file"], line=r["line"]) for r in rows]


def callers_of(cache: IndexCache, callee_name: str) -> list[Location]:
    """Find every call site whose callee identifier matches the given name."""
    rows = cache.conn.execute(
        "SELECT file, line FROM call_sites WHERE callee = ? ORDER BY file, line",
        (callee_name,),
    ).fetchall()
    return [Location(file=r["file"], line=r["line"]) for r in rows]
