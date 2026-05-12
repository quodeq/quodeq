import json
from pathlib import Path
from typing import Any

import pytest
from flask import Flask

from quodeq.api.routes_verifier import register_routes_verifier
from quodeq.verifier.service import LocatedFinding, VerifierService


def _make_project(root: Path) -> None:
    (root / "services").mkdir(parents=True, exist_ok=True)
    (root / "api").mkdir(parents=True, exist_ok=True)
    (root / "services" / "base.py").write_text(
        "from typing import Protocol\nclass ActionProvider(Protocol):\n    ...\n"
    )
    (root / "services" / "filesystem.py").write_text(
        "from services.base import ActionProvider\n"
        "class FilesystemActionProvider(ActionProvider):\n    pass\n"
    )
    (root / "api" / "app.py").write_text(
        "from services.base import ActionProvider\n\n\n"
        "def _default_provider() -> ActionProvider:\n"
        "    from services.filesystem import FilesystemActionProvider\n"
        "    return FilesystemActionProvider()\n\n\n"
        "def create_app(provider: ActionProvider | None = None):\n"
        "    provider = provider or _default_provider()\n"
        "    return provider\n"
    )


def _canned_response() -> dict[str, Any]:
    return {
        "checklist": {
            "Q1": {"answer": "yes", "cite": "MANIFEST"},
            "Q2": {"answer": "yes", "cite": "api/app.py:5"},
            "Q3": {"answer": "yes", "cite": "MANIFEST"},
            "Q4": {"answer": "yes", "cite": "MANIFEST"},
        },
        "confidence": 0.9,
        "evidence_summary": "ok",
    }


@pytest.fixture
def app_with_routes(tmp_path: Path, stub_client):
    _make_project(tmp_path)

    def locate(eval_id: str, dim: str, fid: str) -> LocatedFinding | None:
        if eval_id == "eval-1" and fid == "f1":
            return LocatedFinding(
                file="api/app.py",
                line=5,
                category="flexibility/Adaptability",
                severity="major",
                description="hardcoded dependency",
            )
        return None

    service = VerifierService(
        evaluations_root=tmp_path / "evals",
        project_root=tmp_path,
        finding_locator=locate,
        client=stub_client(_canned_response()),
        model="gemma:4",
    )
    app = Flask(__name__)
    register_routes_verifier(app, service)
    return app


def test_post_verify_creates_verification(app_with_routes):
    client = app_with_routes.test_client()
    resp = client.post("/api/evaluations/eval-1/verify/flexibility/f1")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "verification_id" in data
    assert data["verdict"] in ("false_positive", "inconclusive")
    assert "checklist" in data


def test_post_verify_returns_404_for_missing_finding(app_with_routes):
    client = app_with_routes.test_client()
    resp = client.post("/api/evaluations/eval-1/verify/flexibility/missing")
    assert resp.status_code == 404


def test_get_verifications_list_returns_empty_for_unknown_eval(app_with_routes):
    client = app_with_routes.test_client()
    resp = client.get("/api/evaluations/unknown/verifications")
    assert resp.status_code == 200
    assert resp.get_json() == {"verifications": []}


def test_get_verifications_list_after_verify(app_with_routes):
    client = app_with_routes.test_client()
    client.post("/api/evaluations/eval-1/verify/flexibility/f1")
    resp = client.get("/api/evaluations/eval-1/verifications")
    assert resp.status_code == 200
    items = resp.get_json()["verifications"]
    assert len(items) == 1
    assert items[0]["verdict"] in ("false_positive", "inconclusive")


def test_get_verification_detail_returns_audit_log_paths(app_with_routes):
    client = app_with_routes.test_client()
    post = client.post("/api/evaluations/eval-1/verify/flexibility/f1")
    vid = post.get_json()["verification_id"]
    detail = client.get(f"/api/evaluations/eval-1/verifications/{vid}")
    assert detail.status_code == 200
    data = detail.get_json()
    assert data["verification_id"] == vid
    assert "manifest" in data
    assert "checklist" in data
    assert "raw_response" in data


def test_post_verify_rejects_path_traversal_in_eval_id(app_with_routes):
    client = app_with_routes.test_client()
    resp = client.post("/api/evaluations/..%2F..%2Fetc/verify/flexibility/f1")
    # Path traversal should be caught (either by validator -> 400, or by Flask URL routing -> 404)
    assert resp.status_code in (400, 404)


def test_post_verify_rejects_slash_in_finding_id(app_with_routes):
    client = app_with_routes.test_client()
    # finding_id with path-traversal-style segment
    resp = client.post("/api/evaluations/eval-1/verify/flexibility/..%2Fbad")
    assert resp.status_code in (400, 404)


def test_get_verification_rejects_invalid_id(app_with_routes):
    client = app_with_routes.test_client()
    resp = client.get("/api/evaluations/eval-1/verifications/..%2F..%2Fetc%2Fpasswd")
    assert resp.status_code in (400, 404)


def test_post_verify_returns_503_on_llm_unreachable(tmp_path: Path):
    _make_project(tmp_path)
    from quodeq.verifier.errors import LLMUnreachableError

    class RaisingClient:
        def chat(self, **_kwargs):
            raise LLMUnreachableError("nope")
        def close(self):
            pass

    def locate(eval_id, dim, fid):
        return LocatedFinding(
            file="api/app.py", line=5,
            category="flexibility/Adaptability", severity="major",
            description="hardcoded dependency",
        )
    service = VerifierService(
        evaluations_root=tmp_path / "evals",
        project_root=tmp_path,
        finding_locator=locate,
        client=RaisingClient(),
        model="gemma:4",
    )
    app = Flask(__name__)
    register_routes_verifier(app, service)
    resp = app.test_client().post("/api/evaluations/eval-1/verify/flexibility/f1")
    assert resp.status_code == 503
    body = resp.get_json()
    assert body["error"] == "llm_unreachable"
    assert "hint" in body


def test_post_verify_returns_504_on_timeout(tmp_path: Path):
    _make_project(tmp_path)
    from quodeq.verifier.errors import VerifierTimeoutError

    class TimingOutClient:
        def chat(self, **_kwargs):
            raise VerifierTimeoutError("slow")
        def close(self):
            pass

    def locate(eval_id, dim, fid):
        return LocatedFinding(
            file="api/app.py", line=5,
            category="flexibility/Adaptability", severity="major",
            description="hardcoded dependency",
        )
    service = VerifierService(
        evaluations_root=tmp_path / "evals",
        project_root=tmp_path,
        finding_locator=locate,
        client=TimingOutClient(),
        model="gemma:4",
    )
    app = Flask(__name__)
    register_routes_verifier(app, service)
    resp = app.test_client().post("/api/evaluations/eval-1/verify/flexibility/f1")
    assert resp.status_code == 504
    assert resp.get_json()["error"] == "verifier_timeout"


def test_post_verify_returns_415_for_unsupported_language(tmp_path: Path, stub_client):
    """A finding in a non-Python file returns 415 with a helpful hint."""
    # Create a project with only a Ruby file (no Python adapter will match)
    (tmp_path / "app.rb").write_text("class Foo\n  def bar; end\nend\n")

    def locate(eval_id, dim, fid):
        return LocatedFinding(
            file="app.rb", line=1,
            category="flexibility/Adaptability", severity="major",
            description="hardcoded dependency",
        )
    service = VerifierService(
        evaluations_root=tmp_path / "evals",
        project_root=tmp_path,
        finding_locator=locate,
        client=stub_client({}),  # never reached
        model="gemma:4",
    )
    app = Flask(__name__)
    register_routes_verifier(app, service)
    resp = app.test_client().post("/api/evaluations/eval-1/verify/flexibility/f1")
    assert resp.status_code == 415
    body = resp.get_json()
    assert body["error"] == "language_not_supported"
    assert ".rb" in body["detail"]
    assert "Python" in body["hint"]
