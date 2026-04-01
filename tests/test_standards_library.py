# tests/test_standards_library.py
import json
import pytest
from quodeq.services.standards_library import StandardsLibraryClient

class FakeHttpClient:
    def __init__(self, responses=None):
        self._responses = responses or {}
    def get_json(self, url, headers=None):
        if url in self._responses:
            return self._responses[url]
        raise ConnectionError(f"Not found: {url}")

INDEX = {
    "version": 1,
    "standards": [
        {"id": "clean-arch", "name": "Clean Architecture", "description": "Test", "principleCount": 2, "requirementCount": 8, "file": "standards/clean-arch.json"},
    ],
}

STANDARD_DATA = {
    "id": "clean-arch", "name": "Clean Architecture", "description": "Test",
    "weight": 1.0, "source": "Martin", "principles": [],
}

def test_fetch_index():
    http = FakeHttpClient({"https://example.com/index.json": INDEX})
    client = StandardsLibraryClient(base_url="https://example.com", http_client=http)
    index = client.fetch_index()
    assert len(index) == 1
    assert index[0]["id"] == "clean-arch"

def test_fetch_standard():
    http = FakeHttpClient({"https://example.com/standards/clean-arch.json": STANDARD_DATA})
    client = StandardsLibraryClient(base_url="https://example.com", http_client=http)
    data = client.fetch_standard("standards/clean-arch.json")
    assert data["id"] == "clean-arch"

def test_import_standard(tmp_path):
    http = FakeHttpClient({"https://example.com/standards/clean-arch.json": STANDARD_DATA})
    client = StandardsLibraryClient(base_url="https://example.com", http_client=http)
    result = client.import_standard("standards/clean-arch.json", tmp_path)
    assert (tmp_path / "clean-arch.json").is_file()
    saved = json.loads((tmp_path / "clean-arch.json").read_text())
    assert saved["managed"] is True
    assert saved["type"] == "community"
    assert saved["origin"] == "standards/clean-arch.json"
    assert saved["origin_hash"] is not None


def test_reimport_same_origin_updates(tmp_path):
    http = FakeHttpClient({"https://example.com/standards/clean-arch.json": STANDARD_DATA})
    client = StandardsLibraryClient(base_url="https://example.com", http_client=http)
    client.import_standard("standards/clean-arch.json", tmp_path)
    # Re-import same origin should succeed (update)
    client.import_standard("standards/clean-arch.json", tmp_path)
    assert (tmp_path / "clean-arch.json").is_file()


def test_import_collision_different_origin_raises(tmp_path):
    # Pre-create a standard with a different origin
    existing = {**STANDARD_DATA, "origin": "other-repo/clean-arch.json", "managed": False, "type": "custom"}
    (tmp_path / "clean-arch.json").write_text(json.dumps(existing))
    http = FakeHttpClient({"https://example.com/standards/clean-arch.json": STANDARD_DATA})
    client = StandardsLibraryClient(base_url="https://example.com", http_client=http)
    with pytest.raises(ValueError, match="already exists"):
        client.import_standard("standards/clean-arch.json", tmp_path)
