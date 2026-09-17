"""Paging for GET /api/standards: the page must be sliced before camelizing.

Sibling to test_standards_routes.py (already at the 240-line cap) rather than
an addition to it.
"""
import json

from quodeq.api.app import create_app


def _two_standard_app(tmp_path):
    evaluators = tmp_path / "evaluators"
    evaluators.mkdir()
    compiled = tmp_path / "compiled"
    compiled.mkdir()
    dims = tmp_path / "dimensions.json"
    dims.write_text(json.dumps({
        "applies": [
            {"id": "security", "weight": 1.2, "iso_25010": "Security", "source": "ISO/IEC 25010:2023"},
            {"id": "maintainability", "weight": 1.0, "iso_25010": "Maintainability", "source": "ISO/IEC 25010:2023"},
        ]
    }))
    for sid, name in (("security", "Security"), ("maintainability", "Maintainability")):
        compiled.joinpath(f"{sid}.json").write_text(json.dumps({
            "id": sid, "name": name, "sources": ["iso25010"],
            "principles": [{"name": "P", "requirements": [{"id": "R-1", "text": "t", "refs": []}]}],
        }))
    return create_app(test_config={
        "TESTING": True,
        "STANDARDS_EVALUATORS_DIR": str(evaluators),
        "STANDARDS_COMPILED_DIR": str(compiled),
        "STANDARDS_DIMENSIONS_FILE": str(dims),
    })


def test_list_standards_pages_before_camelizing(tmp_path, monkeypatch):
    app = _two_standard_app(tmp_path)

    import quodeq.api.standards_read_routes as _mod
    real_to_camel_dict = _mod.to_camel_dict
    calls = {"n": 0}

    def counting(*a, **kw):
        calls["n"] += 1
        return real_to_camel_dict(*a, **kw)

    monkeypatch.setattr(_mod, "to_camel_dict", counting)

    with app.test_client() as c:
        resp = c.get("/api/standards?offset=1&limit=1")

    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 1
    assert calls["n"] == 1, "only the paged item must be camelized"


def test_list_standards_paging_matches_full_list_slice(tmp_path):
    app = _two_standard_app(tmp_path)
    with app.test_client() as c:
        full = c.get("/api/standards").get_json()
        paged = c.get("/api/standards?offset=1&limit=1").get_json()
    assert paged == full[1:2]
