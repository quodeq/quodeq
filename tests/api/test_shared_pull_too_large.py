"""POST /api/shared/projects/<project>/pull over the export size cap.

The size-limit failure gets its own wire code (``PULL_TOO_LARGE``) and the
service's own actionable message, so the card can say which knob to turn
instead of the file-upload copy that ``TOO_LARGE`` maps to.
"""
from __future__ import annotations

from quodeq.services.project_archive_export import ExportSizeLimitError
from tests.api.test_shared_pull import (  # noqa: F401 -- fixtures
    _pull,
    app,
    client,
    local_eval_dir,
    pull_slot,
    uuid_named_shared_clone_fixture,
)

_LIMIT_MESSAGE = (
    "Project exceeds maximum export size of 1 MB compressed. "
    "Reduce the project size or increase QUODEQ_MAX_ZIP_SIZE_MB."
)


def test_pull_over_the_size_cap_reports_pull_too_large(
    client, uuid_named_shared_clone_fixture, local_eval_dir, monkeypatch, pull_slot,
):
    _, project_uuid = uuid_named_shared_clone_fixture

    def _too_large(_path):
        raise ExportSizeLimitError(_LIMIT_MESSAGE)

    monkeypatch.setattr("quodeq.api.routes_shared_pull.build_project_zip", _too_large)
    assert _pull(client, project_uuid).status_code == 202

    pull = client.get("/api/shared/status").get_json()["pull"]
    assert pull["code"] == "PULL_TOO_LARGE"
    assert pull["error"] == _LIMIT_MESSAGE


def test_pull_other_value_error_is_an_export_error(
    client, uuid_named_shared_clone_fixture, local_eval_dir, monkeypatch, pull_slot,
):
    _, project_uuid = uuid_named_shared_clone_fixture

    def _bad_timestamp(_path):
        raise ValueError("ZIP does not support timestamps before 1980")

    monkeypatch.setattr("quodeq.api.routes_shared_pull.build_project_zip", _bad_timestamp)
    _pull(client, project_uuid)

    slot = pull_slot.copy()
    assert slot["code"] == "EXPORT_ERROR"
    assert "1980" not in slot["error"]
