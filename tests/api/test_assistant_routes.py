"""Assistant session creation: provider checks, run/repo resolution and source scoping."""
import json

from quodeq.data.sqlite.assistant_repository import AssistantRepository
from tests.api._assistant_routes_fixtures import (  # noqa: F401 -- app/client are pytest fixtures
    _repo,
    app,
    client,
)


def test_create_session(client):
    resp = client.post("/api/assistant/sessions", json={"provider": "ollama", "model": "m"})
    assert resp.status_code == 201
    assert resp.get_json()["sessionId"]


def test_create_session_rejects_unknown_provider(client):
    assert client.post("/api/assistant/sessions", json={"provider": "nope"}).status_code == 400


def test_create_session_accepts_cli_provider(client):
    resp = client.post("/api/assistant/sessions", json={"provider": "claude", "model": "sonnet"})
    assert resp.status_code == 201
    assert resp.get_json()["sessionId"]


def test_create_session_resolves_run_from_project_and_run_id(client, app, monkeypatch, tmp_path):
    # a resolver stub standing in for the real services lookup
    run_dir = tmp_path / "proj-uuid" / "run-9"
    run_dir.mkdir(parents=True)
    monkeypatch.setattr(
        "quodeq.api._assistant_helpers.resolve_run_location",
        lambda project_id, run_id: (str(run_dir), "/src/selectives-android"),
    )
    monkeypatch.setattr(
        "quodeq.api._assistant_helpers.repo_attach_info",
        lambda project_id: ("/src/selectives-android", "ok"),
    )
    resp = client.post("/api/assistant/sessions",
                       json={"provider": "ollama", "projectId": "selectives", "runId": "run-9"})
    assert resp.status_code == 201
    sid = resp.get_json()["sessionId"]
    from quodeq.data.sqlite.assistant_repository import AssistantRepository
    sess = AssistantRepository(app.config["ASSISTANT_DB_PATH"]).get_session(sid)
    assert sess["run_id"] == str(run_dir)
    assert sess["project_uuid"] == "/src/selectives-android"
    assert sess["project_id"] == "selectives"


def test_create_session_stores_project_id_without_run(client, app):
    resp = client.post("/api/assistant/sessions",
                       json={"provider": "ollama", "projectId": "selectives"})
    assert resp.status_code == 201
    sid = resp.get_json()["sessionId"]
    from quodeq.data.sqlite.assistant_repository import AssistantRepository
    sess = AssistantRepository(app.config["ASSISTANT_DB_PATH"]).get_session(sid)
    assert sess["project_id"] == "selectives"
    # No runId supplied → run stays unscoped. Detail tools read the accumulated
    # (per-dimension-latest) composition via project_id, not a single run.
    assert sess["run_id"] is None


def test_client_supplied_rundir_repo_root_are_ignored(client, app, monkeypatch):
    # Client-supplied runDir/repoRoot must NOT be stored verbatim -- they'd
    # flow to the MCP subprocess's --run-dir/--repo-root with no path jail,
    # giving arbitrary server-side file access. Without projectId/runId the
    # session must stay unscoped, not adopt the raw client values.
    monkeypatch.setattr("quodeq.api._assistant_helpers.resolve_run_location",
                        lambda *a: (_ for _ in ()).throw(AssertionError("should not resolve")))
    resp = client.post("/api/assistant/sessions",
                       json={"provider": "ollama", "runDir": "/explicit/run", "repoRoot": "/explicit/repo"})
    assert resp.status_code == 201
    sid = resp.get_json()["sessionId"]
    from quodeq.data.sqlite.assistant_repository import AssistantRepository
    sess = AssistantRepository(app.config["ASSISTANT_DB_PATH"]).get_session(sid)
    assert sess["run_id"] != "/explicit/run"
    assert sess["project_uuid"] != "/explicit/repo"
    assert sess["run_id"] is None
    assert sess["project_uuid"] is None


def test_resolve_run_location_rejects_path_traversal(monkeypatch, tmp_path):
    # Evaluations root with a real run inside it, plus a sibling dir OUTSIDE
    # the root that a "../.." project id could otherwise reach.
    evals = tmp_path / "evaluations"
    (evals / "proj" / "run-1").mkdir(parents=True)
    outside = tmp_path / "outside" / "run-1"
    outside.mkdir(parents=True)
    monkeypatch.setattr(
        "quodeq.api._assistant_helpers.get_evaluations_dir", lambda: str(evals)
    )
    from quodeq.api._assistant_helpers import resolve_run_location
    # A traversal project id that would escape the root must NOT resolve, even
    # though the escaped target ("../outside/run-1") exists on disk.
    assert resolve_run_location("../outside", "run-1") == (None, None)
    assert resolve_run_location("../..", "outside") == (None, None)
    # Sanity: a legit project id still resolves inside the root.
    run_dir, _ = resolve_run_location("proj", "run-1")
    assert run_dir == str((evals / "proj" / "run-1").resolve())


def test_resolve_repo_root_returns_local_working_copy(monkeypatch, tmp_path):
    evals = tmp_path / "evaluations"
    (evals / "proj").mkdir(parents=True)
    repo_dir = tmp_path / "src" / "client-app"
    repo_dir.mkdir(parents=True)
    (evals / "proj" / "repository_info.json").write_text(
        json.dumps({"path": str(repo_dir)}), encoding="utf-8"
    )
    monkeypatch.setattr(
        "quodeq.api._assistant_helpers.get_evaluations_dir", lambda: str(evals)
    )
    from quodeq.api._assistant_helpers import resolve_repo_root
    assert resolve_repo_root("proj") == str(repo_dir)


def test_resolve_repo_root_rejects_urls_and_missing_dirs(monkeypatch, tmp_path):
    # Online projects record a URL as their path; moved repos record a dir
    # that no longer exists. Neither is a readable working copy, so the
    # session must stay detached rather than carry a bogus repo root.
    evals = tmp_path / "evaluations"
    for name, path in (
        ("online", "https://github.com/acme/app"),
        ("ssh", "git@github.com:acme/app.git"),
        ("moved", str(tmp_path / "gone")),
    ):
        (evals / name).mkdir(parents=True)
        (evals / name / "repository_info.json").write_text(
            json.dumps({"path": path}), encoding="utf-8"
        )
    monkeypatch.setattr(
        "quodeq.api._assistant_helpers.get_evaluations_dir", lambda: str(evals)
    )
    from quodeq.api._assistant_helpers import resolve_repo_root
    assert resolve_repo_root("online") is None
    assert resolve_repo_root("ssh") is None
    assert resolve_repo_root("moved") is None
    assert resolve_repo_root("nonexistent") is None


def test_resolve_run_location_detaches_unreadable_repo_root(monkeypatch, tmp_path):
    # Run-scoped resolution applies the same working-copy guard: an online
    # project's URL path must not ride along as a bogus repo root.
    evals = tmp_path / "evaluations"
    (evals / "proj" / "run-1").mkdir(parents=True)
    (evals / "proj" / "repository_info.json").write_text(
        json.dumps({"path": "https://github.com/acme/app"}), encoding="utf-8"
    )
    monkeypatch.setattr(
        "quodeq.api._assistant_helpers.get_evaluations_dir", lambda: str(evals)
    )
    from quodeq.api._assistant_helpers import resolve_run_location
    run_dir, repo_root = resolve_run_location("proj", "run-1")
    assert run_dir == str((evals / "proj" / "run-1").resolve())
    assert repo_root is None


def test_create_session_attaches_repo_root_without_run(client, app, monkeypatch):
    # Overview/accumulated views send projectId with no runId. The repo root
    # is a project-level fact, so it must attach anyway; otherwise repo tools
    # fail with "no analyzed repository attached" in the app's default state.
    monkeypatch.setattr(
        "quodeq.api._assistant_helpers.repo_attach_info",
        lambda project_id: ("/src/selectives-android", "ok"),
    )
    resp = client.post("/api/assistant/sessions",
                       json={"provider": "ollama", "projectId": "selectives"})
    assert resp.status_code == 201
    sid = resp.get_json()["sessionId"]
    sess = AssistantRepository(app.config["ASSISTANT_DB_PATH"]).get_session(sid)
    assert sess["project_uuid"] == "/src/selectives-android"
    assert sess["run_id"] is None  # run scope untouched: still accumulated


def test_create_session_reports_attachment(client, monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setattr("quodeq.api._assistant_helpers.repo_attach_info",
                        lambda pid: (str(repo), "ok"))
    resp = client.post("/api/assistant/sessions",
                       json={"provider": "ollama", "projectId": "p1"})
    data = resp.get_json()
    assert data["repoAttached"] is True
    assert data["repoReason"] == "ok"
    assert data["writeAvailable"] is True


def test_create_session_reports_detachment(client, monkeypatch):
    monkeypatch.setattr("quodeq.api._assistant_helpers.repo_attach_info",
                        lambda pid: (None, "path_missing"))
    resp = client.post("/api/assistant/sessions",
                       json={"provider": "ollama", "projectId": "p1"})
    data = resp.get_json()
    assert data["repoAttached"] is False
    assert data["repoReason"] == "path_missing"
    assert data["writeAvailable"] is False


def test_create_session_write_unavailable_for_unsafe_provider(client, monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setattr("quodeq.api._assistant_helpers.repo_attach_info",
                        lambda pid: (str(repo), "ok"))
    resp = client.post("/api/assistant/sessions",
                       json={"provider": "gemini", "projectId": "p1"})
    data = resp.get_json()
    assert data["repoAttached"] is True
    assert data["writeAvailable"] is False


# ---- source-aware create route ---------------------------------------------

def test_create_session_rejects_unknown_source(client):
    resp = client.post("/api/assistant/sessions",
                       json={"provider": "ollama", "source": "cloud"})
    assert resp.status_code == 400


def test_create_session_shared_409_when_unconfigured(client, monkeypatch):
    from quodeq.services.shared_settings import SharedSettings
    monkeypatch.setattr("quodeq.api.assistant_routes.read_settings",
                        lambda: SharedSettings(url=None))
    resp = client.post("/api/assistant/sessions",
                       json={"provider": "ollama", "source": "shared"})
    assert resp.status_code == 409
    assert resp.get_json()["code"] == "NO_SHARED_REPO"


def test_create_session_shared_409_when_clone_state_bad(client, monkeypatch):
    from quodeq.services.shared_settings import SharedSettings
    monkeypatch.setattr("quodeq.api.assistant_routes.read_settings",
                        lambda: SharedSettings(url="file:///tmp/fake.git"))
    monkeypatch.setattr("quodeq.api.assistant_routes.read_state", lambda url: "foreign")
    resp = client.post("/api/assistant/sessions",
                       json={"provider": "ollama", "source": "shared"})
    assert resp.status_code == 409
    assert "foreign" in resp.get_json()["error"]
    assert resp.get_json()["code"] == "SHARED_REPO_UNAVAILABLE"


def test_create_session_shared_persists_source_and_read_only(client, app, monkeypatch):
    from quodeq.services.shared_settings import SharedSettings
    monkeypatch.setattr("quodeq.api.assistant_routes.read_settings",
                        lambda: SharedSettings(url="file:///tmp/fake.git"))
    monkeypatch.setattr("quodeq.api.assistant_routes.read_state", lambda url: "ok")
    resp = client.post("/api/assistant/sessions",
                       json={"provider": "ollama", "source": "shared",
                             "projectId": "proj-a"})
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["readOnly"] is True
    assert body["writeAvailable"] is False
    assert body["repoAttached"] is False
    assert body["repoReason"] == "online_project"
    row = _repo(app).get_session(body["sessionId"])
    assert row["source"] == "shared"


def test_create_session_local_reports_read_only_false(client, app):
    resp = client.post("/api/assistant/sessions", json={"provider": "ollama"})
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["readOnly"] is False
    assert _repo(app).get_session(body["sessionId"])["source"] == "local"
