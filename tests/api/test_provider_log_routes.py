"""One registrar serves every local provider's log console."""
from __future__ import annotations

from pathlib import Path

from flask import Flask

from quodeq.api.provider_log_routes import ProviderLog, register_provider_log_routes


def _app(log: ProviderLog) -> Flask:
    app = Flask(__name__)
    register_provider_log_routes(app, log, env={})
    return app


def _spec(path: Path | None, *, availability_route: bool) -> ProviderLog:
    return ProviderLog(
        name="demo", log_path=lambda env=None: path, help="start it",
        availability_route=availability_route,
    )


def test_missing_log_answers_404_with_the_provider_help(tmp_path: Path) -> None:
    resp = _app(_spec(tmp_path / "none.log", availability_route=False)).test_client().get("/api/demo/logs/stream")
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "demo log unavailable", "code": "NOT_FOUND", "help": "start it"}


def test_availability_route_is_registered_only_when_asked(tmp_path: Path) -> None:
    log = tmp_path / "server.log"
    log.write_text("x\n", encoding="utf-8")
    with_route = _app(_spec(log, availability_route=True))
    without = _app(_spec(log, availability_route=False))
    assert with_route.test_client().get("/api/demo/logs/available").get_json() == {"available": True}
    assert without.test_client().get("/api/demo/logs/available").status_code == 404
    assert {r.endpoint for r in with_route.url_map.iter_rules()} >= {"demo_logs_available", "stream_demo_logs"}


def test_stream_is_an_uncached_event_stream(tmp_path: Path) -> None:
    log = tmp_path / "server.log"
    log.write_text("", encoding="utf-8")
    resp = _app(_spec(log, availability_route=False)).test_client().get("/api/demo/logs/stream")
    assert resp.mimetype == "text/event-stream"
    assert resp.headers["Cache-Control"] == "no-cache"
    assert resp.headers["X-Accel-Buffering"] == "no"
    resp.close()
