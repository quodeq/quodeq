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
