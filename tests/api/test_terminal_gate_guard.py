"""The terminal routes' gate guard: a refused gate answers 403 and never runs the handler."""
from __future__ import annotations

from http import HTTPStatus

from flask import Flask, jsonify

from quodeq.api.terminal_routes import gated


def test_an_open_gate_runs_the_handler_with_its_arguments() -> None:
    calls = []

    @gated(lambda: None)
    def handler(registry, sid):
        calls.append((registry, sid))
        return "ran"

    with Flask(__name__).test_request_context():
        assert handler("reg", "s1") == "ran"
    assert calls == [("reg", "s1")]


def test_a_refused_gate_answers_403_without_running_the_handler() -> None:
    calls = []

    @gated(lambda: "remote host")
    def handler():
        calls.append(True)
        return jsonify({"ok": True})

    with Flask(__name__).test_request_context():
        response, status = handler()
        assert status == HTTPStatus.FORBIDDEN
        assert response.get_json() == {"error": "forbidden", "code": "FORBIDDEN"}
    assert calls == []
