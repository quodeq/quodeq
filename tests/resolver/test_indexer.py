from pathlib import Path

from quodeq.resolver.cache import IndexCache
from quodeq.resolver.indexer import build_index


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_indexes_class_and_function_from_one_file(tmp_path: Path):
    _write(
        tmp_path / "src" / "a.py",
        """\
class Foo(Bar):
    pass


def helper(x: int) -> None:
    pass
""",
    )
    db_path = tmp_path / "symbols.db"
    cache = IndexCache(db_path)
    build_index(cache, tmp_path)

    rows = cache.conn.execute("SELECT * FROM classes ORDER BY name").fetchall()
    assert [r["name"] for r in rows] == ["Foo"]
    assert rows[0]["base_list"] == "Bar"

    fn_rows = cache.conn.execute("SELECT * FROM functions ORDER BY name").fetchall()
    assert [r["name"] for r in fn_rows] == ["helper"]
    cache.close()


def test_skips_unsupported_extensions(tmp_path: Path):
    _write(tmp_path / "a.py", "class A:\n    pass\n")
    _write(tmp_path / "b.txt", "ignore me")
    cache = IndexCache(tmp_path / "symbols.db")
    build_index(cache, tmp_path)
    rows = cache.conn.execute("SELECT name FROM classes").fetchall()
    assert [r["name"] for r in rows] == ["A"]
    cache.close()


def test_records_file_hash(tmp_path: Path):
    _write(tmp_path / "a.py", "class A:\n    pass\n")
    cache = IndexCache(tmp_path / "symbols.db")
    build_index(cache, tmp_path)
    row = cache.conn.execute("SELECT * FROM file_hashes").fetchone()
    assert row is not None
    assert row["file"].endswith("a.py")
    assert len(row["sha256"]) == 64
    cache.close()


def test_build_index_skips_unchanged_files(tmp_path: Path):
    """A second build_index call on the same content skips all files."""
    _write(
        tmp_path / "a.py",
        "class Foo:\n    pass\n",
    )
    cache = IndexCache(tmp_path / "symbols.db", parser_version="0.23.2")
    first = build_index(cache, tmp_path)
    assert first["parsed"] == 1
    assert first["skipped"] == 0

    # Run again with no changes
    second = build_index(cache, tmp_path)
    assert second["parsed"] == 0
    assert second["skipped"] == 1
    cache.close()


def test_build_index_reparses_changed_files(tmp_path: Path):
    """Changing a file's content causes it to be re-parsed."""
    _write(
        tmp_path / "a.py",
        "class Foo:\n    pass\n",
    )
    cache = IndexCache(tmp_path / "symbols.db", parser_version="0.23.2")
    build_index(cache, tmp_path)

    # Edit the file
    _write(
        tmp_path / "a.py",
        "class Foo:\n    pass\n\nclass Bar:\n    pass\n",
    )
    result = build_index(cache, tmp_path)
    assert result["parsed"] == 1
    assert result["skipped"] == 0
    # Verify Bar is now indexed
    rows = cache.conn.execute("SELECT name FROM classes ORDER BY name").fetchall()
    assert [r["name"] for r in rows] == ["Bar", "Foo"]
    cache.close()


def test_build_index_removes_deleted_files(tmp_path: Path):
    """A file removed from disk has its rows removed from the index."""
    _write(
        tmp_path / "a.py",
        "class Foo:\n    pass\n",
    )
    _write(
        tmp_path / "b.py",
        "class Bar:\n    pass\n",
    )
    cache = IndexCache(tmp_path / "symbols.db", parser_version="0.23.2")
    build_index(cache, tmp_path)

    # Delete a.py
    (tmp_path / "a.py").unlink()
    result = build_index(cache, tmp_path)
    assert result["removed"] == 1
    rows = cache.conn.execute("SELECT name FROM classes").fetchall()
    assert [r["name"] for r in rows] == ["Bar"]
    cache.close()
