"""Tests for Standards API read and write endpoints."""
import json
from pathlib import Path
import pytest
from quodeq.api.app import create_app

@pytest.fixture()
def dirs(tmp_path):
    evaluators = tmp_path / "evaluators"
    evaluators.mkdir()
    compiled = tmp_path / "compiled"
    compiled.mkdir()
    dims = tmp_path / "dimensions.json"
    dims.write_text(json.dumps({
        "applies": [{"id": "security", "weight": 1.2, "iso_25010": "Security", "source": "ISO/IEC 25010:2023"}]
    }))
    compiled.joinpath("security.json").write_text(json.dumps({
        "id": "security", "name": "Security", "sources": ["iso25010"],
        "principles": [{"name": "Confidentiality", "requirements": [{"id": "S-1", "text": "Test req", "refs": []}]}],
    }))
    return {"evaluators": evaluators, "compiled": compiled, "dimensions": dims}

@pytest.fixture()
def client(dirs):
    app = create_app(test_config={
        "TESTING": True,
        "STANDARDS_EVALUATORS_DIR": str(dirs["evaluators"]),
        "STANDARDS_COMPILED_DIR": str(dirs["compiled"]),
        "STANDARDS_DIMENSIONS_FILE": str(dirs["dimensions"]),
    })
    with app.test_client() as c:
        yield c

# Read endpoints
def test_list_standards(client):
    resp = client.get("/api/standards")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert any(s["id"] == "security" for s in data)

def test_get_standard_detail(client):
    resp = client.get("/api/standards/security")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["id"] == "security"
    assert "principles" in data

def test_get_standard_not_found(client):
    resp = client.get("/api/standards/nonexistent")
    assert resp.status_code == 404
