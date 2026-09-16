"""load_taxonomy() reads a dimension's compiled file; absent or malformed -> EMPTY_TAXONOMY."""
from __future__ import annotations

import json

from quodeq.core.taxonomy import EMPTY_TAXONOMY
from quodeq.data.fs.standards_loader import load_taxonomy


def _write(compiled_dir, dimension, data):
    compiled_dir.mkdir(parents=True, exist_ok=True)
    (compiled_dir / f"{dimension}.json").write_text(json.dumps(data), encoding="utf-8")


def test_loads_taxonomy_from_compiled_file(tmp_path):
    compiled = tmp_path / "compiled"
    _write(compiled, "reliability", {
        "id": "reliability", "taxonomy_version": "2026-09-16",
        "principles": [{"name": "Fault Tolerance", "requirements": [
            {"id": "R-FT-1", "text": "...", "violation_types": [{"code": "empty-catch-block"}]},
        ]}],
    })
    tax = load_taxonomy(compiled, "reliability")
    assert tax.version == "2026-09-16"
    assert tax.for_requirement("R-FT-1").codes == ("empty-catch-block",)


def test_missing_file_is_empty_taxonomy(tmp_path):
    (tmp_path / "compiled").mkdir()
    assert load_taxonomy(tmp_path / "compiled", "reliability") is EMPTY_TAXONOMY


def test_malformed_block_is_logged_and_empty(tmp_path, caplog):
    compiled = tmp_path / "compiled"
    _write(compiled, "reliability", {
        "id": "reliability",
        "principles": [{"name": "FT", "requirements": [
            {"id": "R-FT-1", "violation_types": [{"code": "other"}]},
        ]}],
    })
    with caplog.at_level("WARNING"):
        tax = load_taxonomy(compiled, "reliability")
    assert tax is EMPTY_TAXONOMY
    assert "Ignoring taxonomy for reliability" in caplog.text
