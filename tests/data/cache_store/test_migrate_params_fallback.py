"""derive_params_hash falls back to "" on an unreadable or invalid-JSON compiled file."""
from __future__ import annotations

from pathlib import Path

from quodeq.data.cache_store.migrate import derive_params_hash

_EFFECTIVE = {"req-1": {"threshold": 3}}


def test_invalid_json_compiled_params_falls_back_to_empty_hash(tmp_path: Path) -> None:
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir()
    (compiled_dir / "security.json").write_text("not json", encoding="utf-8")
    assert derive_params_hash("security", _EFFECTIVE, tmp_path) == ""


def test_missing_compiled_params_falls_back_to_empty_hash(tmp_path: Path) -> None:
    # standards_dir exists but the compiled/<dimension>.json file does not.
    assert derive_params_hash("security", _EFFECTIVE, tmp_path) == ""
