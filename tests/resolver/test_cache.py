from pathlib import Path

from quodeq.resolver.cache import IndexCache


def test_cache_creates_db(tmp_path: Path):
    db = tmp_path / "symbols.db"
    cache = IndexCache(db)
    assert db.exists()
    cache.close()


def test_cache_schema_tables_present(tmp_path: Path):
    cache = IndexCache(tmp_path / "symbols.db")
    tables = cache.list_tables()
    assert "classes" in tables
    assert "functions" in tables
    assert "function_params" in tables
    assert "imports" in tables
    assert "call_sites" in tables
    assert "file_hashes" in tables
    assert "meta" in tables
    cache.close()


def test_cache_wal_mode(tmp_path: Path):
    cache = IndexCache(tmp_path / "symbols.db")
    mode = cache.conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"
    cache.close()


def test_cache_meta_records_parser_version(tmp_path: Path):
    cache = IndexCache(tmp_path / "symbols.db", parser_version="0.23.2")
    rec = cache.get_meta("parser_version")
    assert rec == "0.23.2"
    cache.close()


def test_cache_meta_round_trip(tmp_path: Path):
    cache = IndexCache(tmp_path / "symbols.db")
    cache.set_meta("built_at_sha", "abc123")
    assert cache.get_meta("built_at_sha") == "abc123"
    cache.close()
