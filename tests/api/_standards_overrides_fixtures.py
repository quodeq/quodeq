"""Shared fixtures for tests/api/test_standards_overrides_routes*.py siblings."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.api.app import create_app


OVERRIDES_URL = "/api/projects/proj-1/standards-overrides"


def _write_compiled_dim(compiled_dir: Path) -> None:
    (compiled_dir / "maintainability.json").write_text(json.dumps({
        "id": "maintainability",
        "principles": [{"name": "Analyzability", "requirements": [{
            "id": "M-ANA-2",
            "text": "Functions MUST NOT exceed {max_lines} lines",
            "params": {"max_lines": {"label": "Max function lines", "type": "int",
                                     "default": 50, "min": 10, "max": 500}},
        }]}],
    }))


@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    return root


@pytest.fixture()
def client(tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch):
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir()
    _write_compiled_dim(compiled_dir)

    dims = tmp_path / "dimensions.json"
    dims.write_text(json.dumps({"applies": []}))
    evaluators = tmp_path / "evaluators"
    evaluators.mkdir()

    app = create_app(test_config={
        "TESTING": True,
        "STANDARDS_EVALUATORS_DIR": str(evaluators),
        "STANDARDS_COMPILED_DIR": str(compiled_dir),
        "STANDARDS_DIMENSIONS_FILE": str(dims),
    })

    import quodeq.api.standards_overrides_routes as _mod
    monkeypatch.setattr(_mod, "resolve_repo_root", lambda pid: str(project_root) if pid == "proj-1" else None)

    with app.test_client() as c:
        yield c


@pytest.fixture()
def client_without_repo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir()

    dims = tmp_path / "dimensions.json"
    dims.write_text(json.dumps({"applies": []}))
    evaluators = tmp_path / "evaluators"
    evaluators.mkdir()

    app = create_app(test_config={
        "TESTING": True,
        "STANDARDS_EVALUATORS_DIR": str(evaluators),
        "STANDARDS_COMPILED_DIR": str(compiled_dir),
        "STANDARDS_DIMENSIONS_FILE": str(dims),
    })

    import quodeq.api.standards_overrides_routes as _mod
    monkeypatch.setattr(_mod, "resolve_repo_root", lambda pid: None)

    with app.test_client() as c:
        yield c


_LOCALHOST = {"Origin": "http://localhost"}


def _write_evaluator_dim(evaluators_dir: Path) -> None:
    """Write a custom standard with its own params-bearing requirement."""
    (evaluators_dir / "custom-standard.json").write_text(json.dumps({
        "id": "custom-standard",
        "type": "custom",
        "managed": False,
        "principles": [{"name": "Custom Principle", "requirements": [{
            "id": "CUST-1",
            "text": "Custom rule MUST NOT exceed {max_items} items",
            "params": {"max_items": {"label": "Max items", "type": "int",
                                     "default": 100, "min": 1, "max": 1000}},
        }]}],
    }))


@pytest.fixture()
def client_with_custom(tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch):
    """Client fixture with a custom standard in evaluators_dir."""
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir()
    _write_compiled_dim(compiled_dir)

    dims = tmp_path / "dimensions.json"
    dims.write_text(json.dumps({"applies": []}))
    evaluators = tmp_path / "evaluators"
    evaluators.mkdir()
    _write_evaluator_dim(evaluators)

    app = create_app(test_config={
        "TESTING": True,
        "STANDARDS_EVALUATORS_DIR": str(evaluators),
        "STANDARDS_COMPILED_DIR": str(compiled_dir),
        "STANDARDS_DIMENSIONS_FILE": str(dims),
    })

    import quodeq.api.standards_overrides_routes as _mod
    monkeypatch.setattr(_mod, "resolve_repo_root", lambda pid: str(project_root) if pid == "proj-1" else None)

    with app.test_client() as c:
        yield c
