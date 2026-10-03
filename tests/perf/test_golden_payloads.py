"""Golden payloads: today's scores, frozen.

The backend work in the perf plan changes how scores are read and cached,
not what they are. These tests hold the JSON the dashboard's score routes
return for a fixed project (``_golden_fixture``) to the snapshots in
``golden/``. Anything that changes a grade, a count, a trend, or which
findings a dismissal, a deletion or a suppression rule removes fails here.

Volatile values (ISO timestamps) are replaced before comparing.

A change that is meant to alter scores regenerates the snapshots with
``QUODEQ_UPDATE_GOLDEN=1`` and says why in its PR.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from quodeq.api.app import create_app
from tests.perf._golden_fixture import (
    CHILD_PROJECT, LATEST_RUN_ID, MIDDLE_RUN_ID, PROJECT, seed_golden_project,
)

pytestmark = pytest.mark.real_standards

GOLDEN_DIR = Path(__file__).with_name("golden")
UPDATE_ENV = "QUODEQ_UPDATE_GOLDEN"
TIMESTAMP_PLACEHOLDER = "<timestamp>"
_ISO_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$")

SNAPSHOTS = {
    "scores_latest": f"/api/projects/{PROJECT}/scores",
    "scores_as_of_middle": f"/api/projects/{PROJECT}/scores?asOf={MIDDLE_RUN_ID}",
    "compare_summary": f"/api/projects/{PROJECT}/compare-summary",
    "compare_summary_child": f"/api/projects/{CHILD_PROJECT}/compare-summary",
    "dashboard_overview_latest": f"/api/projects/{PROJECT}/dashboard?view=overview",
    "dashboard_latest": f"/api/projects/{PROJECT}/dashboard?run={LATEST_RUN_ID}",
    "dashboard_overview_middle": f"/api/projects/{PROJECT}/dashboard?view=overview&run={MIDDLE_RUN_ID}",
    "dashboard_middle": f"/api/projects/{PROJECT}/dashboard?run={MIDDLE_RUN_ID}",
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("QUODEQ_API_KEY", raising=False)
    reports = tmp_path / "evaluations"
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(reports))
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "index.db"))
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "score_cache.db"))
    seed_golden_project(reports)
    return create_app(static_dist=None, api_key=None).test_client()


def normalise(value):
    """The payload with every ISO timestamp replaced by a placeholder."""
    if isinstance(value, dict):
        return {k: normalise(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalise(v) for v in value]
    if isinstance(value, str) and _ISO_TIMESTAMP.match(value):
        return TIMESTAMP_PLACEHOLDER
    return value


def _dump(body) -> str:
    return json.dumps(body, indent=2, sort_keys=True) + "\n"


@pytest.mark.parametrize("name", sorted(SNAPSHOTS))
def test_payload_matches_golden(client, name):
    resp = client.get(SNAPSHOTS[name])
    assert resp.status_code == 200, SNAPSHOTS[name]
    actual = _dump(normalise(resp.get_json()))
    path = GOLDEN_DIR / f"{name}.json"
    if os.environ.get(UPDATE_ENV):
        GOLDEN_DIR.mkdir(exist_ok=True)
        path.write_text(actual, encoding="utf-8")
    assert path.is_file(), f"No golden for {name}; run with {UPDATE_ENV}=1"
    assert actual == path.read_text(encoding="utf-8"), (
        f"{name} changed. If the scores are meant to change, rerun with {UPDATE_ENV}=1 and explain why in the PR."
    )


def test_golden_dir_has_no_stale_snapshots():
    names = {p.stem for p in GOLDEN_DIR.glob("*.json")}
    assert names == set(SNAPSHOTS)
