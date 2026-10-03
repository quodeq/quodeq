"""A stored eval's deferred rows refill from /compliance-detail?run= by identity.

The eval route and the detail route read the run through different paths
(the evaluation file vs the rescored lists), so this checks on the golden
project (a dismissal, a deletion and a suppression rule in play) that every
deferred eval row has a full row with the same identity (file, line,
endLine, principle, title) in the detail response, the match the UI's
mergeFindingDetail makes.
"""
from __future__ import annotations

import pytest

from quodeq.api.app import create_app
from quodeq.services.scoring.compliance_detail import DETAIL_FIELDS
from tests.perf._golden_fixture import LATEST_RUN_ID, PROJECT, seed_golden_project

_RUN = LATEST_RUN_ID
_EVAL = f"/api/projects/{PROJECT}/runs/{_RUN}/dimensions/security/eval"
_DETAIL = f"/api/projects/{PROJECT}/compliance-detail?dimension=security&kind=violation&run={_RUN}"


def _identity(row: dict) -> tuple:
    return (row.get("file"), row.get("line"), row.get("endLine"), row.get("practiceId"), row.get("title"))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("QUODEQ_API_KEY", raising=False)
    reports = tmp_path / "evaluations"
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(reports))
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "index.db"))
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "score_cache.db"))
    seed_golden_project(reports)
    return create_app(static_dist=None, api_key=None).test_client()


def test_stored_eval_rows_are_deferred_and_refill_by_identity(client) -> None:
    eval_body = client.get(_EVAL).get_json()
    rows = eval_body["violations"]
    assert rows and all(r["detailDeferred"] and not (set(r) & DETAIL_FIELDS) for r in rows)

    detail = client.get(_DETAIL).get_json()["items"]
    assert all(d["snippet"] for d in detail)
    assert sorted(_identity(r) for r in rows) == sorted(_identity(d) for d in detail)
