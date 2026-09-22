"""Body type validation for the findings mutation endpoints."""
from tests.api._routes_findings_fixtures import app, client  # noqa: F401 -- pytest fixtures


class TestBodyTypeValidation:
    """REL-038/039/040/041: malformed field types must 400 at the API
    boundary instead of crashing in the service layer (a 500)."""

    def test_dismiss_rejects_list_req(self, client, tmp_path):
        (tmp_path / "my-project").mkdir()
        resp = client.post("/api/findings/dismiss", json={
            "project": "my-project", "req": ["M-MOD-4"], "file": "foo.js", "line": 4,
        })
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"

    def test_dismiss_rejects_string_line(self, client, tmp_path):
        (tmp_path / "my-project").mkdir()
        resp = client.post("/api/findings/dismiss", json={
            "project": "my-project", "req": "M-MOD-4", "file": "foo.js", "line": "4",
        })
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"

    def test_dismiss_rejects_bool_line(self, client, tmp_path):
        (tmp_path / "my-project").mkdir()
        resp = client.post("/api/findings/dismiss", json={
            "project": "my-project", "req": "M-MOD-4", "file": "foo.js", "line": True,
        })
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"

    def test_restore_rejects_dict_file(self, client, tmp_path):
        (tmp_path / "my-project").mkdir()
        resp = client.post("/api/findings/restore", json={
            "project": "my-project", "req": "M-MOD-4", "file": {"p": "foo.js"}, "line": 4,
        })
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"

    def test_delete_rejects_list_dimension(self, client, tmp_path):
        (tmp_path / "my-project").mkdir()
        resp = client.post("/api/findings/delete", json={
            "project": "my-project", "dimension": ["security"],
            "principle": "Integrity", "file": "foo.js",
        })
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"

    def test_unverify_rejects_int_req(self, client, tmp_path):
        (tmp_path / "my-project").mkdir()
        resp = client.post("/api/findings/unverify", json={
            "project": "my-project", "req": 7, "file": "a.py", "line": 3,
        })
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "INVALID_PARAM"

    def test_missing_fields_still_report_missing_param(self, client):
        # The MISSING_PARAM contract for absent fields is unchanged.
        resp = client.post("/api/findings/dismiss", json={"project": "x"})
        assert resp.status_code == 400
        assert resp.get_json()["code"] == "MISSING_PARAM"
