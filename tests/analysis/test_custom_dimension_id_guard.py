import json
from pathlib import Path
from quodeq.analysis._analysis_context import _load_custom_dimensions

def test_traversal_evaluator_id_is_skipped(tmp_path: Path):
    (tmp_path / "evil.json").write_text(json.dumps({"id": "../../etc/passwd"}), encoding="utf-8")
    (tmp_path / "slash.json").write_text(json.dumps({"id": "a/b"}), encoding="utf-8")
    (tmp_path / "ok.json").write_text(json.dumps({"id": "my-eval"}), encoding="utf-8")
    result = _load_custom_dimensions(tmp_path, [])
    assert "my-eval" in result
    assert "../../etc/passwd" not in result
    assert "a/b" not in result
