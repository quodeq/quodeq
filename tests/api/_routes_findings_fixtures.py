"""Shared fixtures for tests/api/test_routes_findings*.py siblings."""
from __future__ import annotations

import pytest
from flask import Flask

from quodeq.api.routes_findings import register_findings_routes


@pytest.fixture()
def app(tmp_path):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["EVALUATIONS_DIR"] = str(tmp_path)
    register_findings_routes(app)
    return app


@pytest.fixture()
def client(app):
    return app.test_client()
