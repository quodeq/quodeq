"""ToolContext carries the visible-standards selection; build_tool_context
(the API construction site) resolves it from the project's
``.quodeq/standards-visibility.json``.

tests/assistant has no conftest.py, and the suite's convention is a small
local ``_ctx``/fixture helper per file (see test_registry.py, test_tools_
overview.py) rather than shared factories -- followed here instead of the
``tool_context_factory``/``api_tool_context`` names sketched in the task
brief, which don't exist in this repo.
"""
from __future__ import annotations

import argparse

from flask import Flask

from quodeq.api._assistant_helpers import build_tool_context
from quodeq.assistant.tools._context import ToolContext
from quodeq.core.standards.visibility import DEFAULT_VISIBLE_STANDARDS
from quodeq.data.fs.standards_prefs import save_visible_standard_ids
from quodeq.data.sqlite.assistant_repository import AssistantRepository
from quodeq.services.shared_settings import SharedSettings


def _ctx(tmp_path, **kw):
    return ToolContext(
        repository=AssistantRepository(tmp_path / "assistant.db"),
        session_id="s", run_dir=None, repo_root=None,
        evaluators_dir=tmp_path, compiled_dir=tmp_path,
        dimensions_file=tmp_path / "dims.json", **kw)


def test_field_defaults_to_none(tmp_path):
    """None == no filtering, so every existing caller keeps today's behaviour."""
    assert _ctx(tmp_path).visible_standard_ids is None


def test_field_accepts_a_tuple(tmp_path):
    ctx = _ctx(tmp_path, visible_standard_ids=("security",))
    assert ctx.visible_standard_ids == ("security",)


def _app(tmp_path):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["ASSISTANT_DB_PATH"] = str(tmp_path / "assistant.db")
    app.config["STANDARDS_EVALUATORS_DIR"] = str(tmp_path / "evaluators")
    app.config["STANDARDS_COMPILED_DIR"] = str(tmp_path / "compiled")
    app.config["STANDARDS_DIMENSIONS_FILE"] = str(tmp_path / "dimensions.json")
    return app


def _session(**kw):
    base = {"id": "s1", "run_id": None, "source": "local",
            "project_uuid": None, "project_id": None}
    base.update(kw)
    return base


def test_api_helper_loads_defaults_for_a_repo_without_a_file(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    app = _app(tmp_path)
    with app.app_context():
        ctx = build_tool_context(app, _session(project_uuid=str(repo_root)))
    assert ctx.visible_standard_ids == DEFAULT_VISIBLE_STANDARDS


def test_api_helper_loads_the_saved_selection(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    save_visible_standard_ids(repo_root, ["security", "clean-architecture"])
    app = _app(tmp_path)
    with app.app_context():
        ctx = build_tool_context(app, _session(project_uuid=str(repo_root)))
    assert ctx.visible_standard_ids == ("security", "clean-architecture")


def test_api_helper_falls_back_to_defaults_when_no_repo_resolves(tmp_path):
    """No repo root still resolves a concrete selection (the ISO defaults),
    not None -- a session with nothing to scope to must not read as
    "unfiltered"."""
    app = _app(tmp_path)
    with app.app_context():
        ctx = build_tool_context(app, _session(project_uuid=None, project_id=None))
    assert ctx.repo_root is None
    assert ctx.visible_standard_ids == DEFAULT_VISIBLE_STANDARDS


def test_api_helper_resolves_repo_root_via_project_id_fallback(tmp_path, monkeypatch):
    # Overview-scoped sessions carry project_id with no project_uuid (the
    # reason build_tool_context grew the fallback); the selection must still
    # resolve for them, not just for run/repo-scoped sessions.
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    save_visible_standard_ids(repo_root, ["performance"])
    resolver = lambda project_id: str(repo_root) if project_id == "proj-x" else None
    app = _app(tmp_path)
    with app.app_context():
        ctx = build_tool_context(
            app, _session(project_uuid=None, project_id="proj-x"),
            repo_root_resolver=resolver)
    assert ctx.repo_root == repo_root
    assert ctx.visible_standard_ids == ("performance",)


def test_api_helper_shared_session_never_falls_back_to_a_local_repo_root(
        tmp_path, monkeypatch):
    # Shared sessions are guaranteed no local working copy at session-creation
    # time (assistant_routes.create_session's shared branch never resolves a
    # repo_root even when projectId is given). The project_id fallback added
    # for the overview case above must not quietly undo that guarantee just
    # because a same-named local project happens to exist on this machine.
    called = []
    resolver = lambda project_id: called.append(project_id) or str(tmp_path)
    monkeypatch.setattr(
        "quodeq.api._assistant_helpers.read_settings",
        lambda: SharedSettings(url="file:///fake-origin.git"),
    )
    monkeypatch.setattr("quodeq.api._assistant_helpers.read_state", lambda url: "ok")
    monkeypatch.setattr(
        "quodeq.api._assistant_helpers.shared_evaluations_root",
        lambda url: tmp_path / "shared",
    )
    monkeypatch.setattr(
        "quodeq.api._assistant_helpers.shared_score_cache_path",
        lambda url: tmp_path / "cache.db",
    )
    app = _app(tmp_path)
    with app.app_context():
        ctx = build_tool_context(
            app, _session(source="shared", project_uuid=None, project_id="proj-x"),
            repo_root_resolver=resolver)
    assert ctx.repo_root is None
    # A shared session still resolves a concrete selection (the ISO
    # defaults), not None -- it gets no filtering-off exemption just because
    # it has no local repo.
    assert ctx.visible_standard_ids == DEFAULT_VISIBLE_STANDARDS
    assert called == []


def test_api_helper_shared_session_gets_defaults_not_none(tmp_path, monkeypatch):
    """A plain shared session (no project_id fallback in play at all) still
    resolves DEFAULT_VISIBLE_STANDARDS. Filtering being silently off for
    shared/online/moved-repo sessions was the original bug re-surfacing in a
    new place; the shared clone has no working copy to scope to, so it must
    fall back to the same defaults a local repo without a file would get."""
    monkeypatch.setattr(
        "quodeq.api._assistant_helpers.read_settings",
        lambda: SharedSettings(url="file:///fake-origin.git"),
    )
    monkeypatch.setattr("quodeq.api._assistant_helpers.read_state", lambda url: "ok")
    monkeypatch.setattr(
        "quodeq.api._assistant_helpers.shared_evaluations_root",
        lambda url: tmp_path / "shared",
    )
    monkeypatch.setattr(
        "quodeq.api._assistant_helpers.shared_score_cache_path",
        lambda url: tmp_path / "cache.db",
    )
    app = _app(tmp_path)
    with app.app_context():
        ctx = build_tool_context(
            app, _session(source="shared", project_uuid=None, project_id=None))
    assert ctx.repo_root is None
    assert ctx.visible_standard_ids == DEFAULT_VISIBLE_STANDARDS


def _capture_ctx(monkeypatch):
    """Patch the module-level ToolContext in server.py with a capturing spy,
    so a test can call the real _build_registry_from_args and then assert on
    the ToolContext it actually constructed (build_registry itself doesn't
    expose ctx, so this is the only way to observe it without touching the
    source).
    """
    from quodeq.assistant.mcp import server as mcp_server
    captured = {}
    real = mcp_server.ToolContext

    def spy(**kwargs):
        ctx = real(**kwargs)
        captured["ctx"] = ctx
        return ctx

    monkeypatch.setattr(mcp_server, "ToolContext", spy)
    return captured


def _mcp_namespace(tmp_path, **kw):
    base = dict(
        db_path=str(tmp_path / "a.db"),
        session_id="mcp-test",
        run_dir=None,
        repo_root=None,
        evaluators_dir=str(tmp_path / "e"),
        compiled_dir=str(tmp_path / "c"),
        dimensions_file=str(tmp_path / "d.json"),
        project_id=None,
        reports_dir="",
        enable_write=False,
        worktree_dir=None,
        read_only=False,
    )
    base.update(kw)
    return argparse.Namespace(**base)


def test_mcp_path_loads_saved_selection(tmp_path, monkeypatch):
    """_build_registry_from_args loads standards-visibility.json onto ToolContext."""
    from quodeq.assistant.mcp.server import _build_registry_from_args

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    save_visible_standard_ids(repo_root, ["security", "clean-architecture"])

    captured = _capture_ctx(monkeypatch)
    ns = _mcp_namespace(tmp_path, repo_root=str(repo_root))
    _build_registry_from_args(ns)

    assert captured["ctx"].visible_standard_ids == ("security", "clean-architecture")


def test_mcp_path_no_repo_root_falls_back_to_defaults(tmp_path, monkeypatch):
    """_build_registry_from_args with no --repo-root still carries a concrete
    selection (the ISO defaults), not None -- an MCP caller with no repo root
    gets the same fallback as every other unresolved-repo session."""
    from quodeq.assistant.mcp.server import _build_registry_from_args

    captured = _capture_ctx(monkeypatch)
    ns = _mcp_namespace(tmp_path, repo_root=None)
    _build_registry_from_args(ns)

    assert captured["ctx"].repo_root is None
    assert captured["ctx"].visible_standard_ids == DEFAULT_VISIBLE_STANDARDS
