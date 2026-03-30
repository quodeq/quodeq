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

# Write endpoints
def test_create_standard(client):
    payload = {"id": "my-std", "name": "My Standard", "description": "Test standard", "weight": 1.0, "source": "Test", "principles": []}
    resp = client.post("/api/standards", json=payload, headers={"Origin": "http://localhost"})
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["id"] == "my-std"
    assert data["type"] == "custom"

def test_update_standard(client):
    client.post("/api/standards", json={"id": "upd-std", "name": "Original", "description": "", "weight": 1.0, "source": "", "principles": []}, headers={"Origin": "http://localhost"})
    resp = client.put("/api/standards/upd-std", json={"id": "upd-std", "name": "Updated", "description": "", "weight": 1.0, "source": "", "principles": []}, headers={"Origin": "http://localhost"})
    assert resp.status_code == 200
    assert resp.get_json()["name"] == "Updated"

def test_delete_standard(client):
    client.post("/api/standards", json={"id": "del-std", "name": "Delete Me", "description": "", "weight": 1.0, "source": "", "principles": []}, headers={"Origin": "http://localhost"})
    resp = client.delete("/api/standards/del-std", headers={"Origin": "http://localhost"})
    assert resp.status_code == 204

def test_delete_builtin_forbidden(client):
    resp = client.delete("/api/standards/security", headers={"Origin": "http://localhost"})
    assert resp.status_code == 403

def test_duplicate_standard(client):
    client.post("/api/standards", json={"id": "src-std", "name": "Source", "description": "", "weight": 1.0, "source": "", "principles": []}, headers={"Origin": "http://localhost"})
    resp = client.post("/api/standards/src-std/duplicate", json={"newId": "copy-std"}, headers={"Origin": "http://localhost"})
    assert resp.status_code == 201
    assert resp.get_json()["id"] == "copy-std"
