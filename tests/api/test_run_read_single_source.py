"""One run, one source: the run page's lists, the detail refill and the
dimension eval agree on which findings a run has.

Pattern suppression rules are the case that used to split them. The SQL
grade-tables read behind ``/scores/<run>`` and ``/compliance-detail?run=``
applied dismissals and deletions (the projection folds them in) but never
loaded ``suppression_rules.json``, while the dimension eval and the
overview did. A project with rules and no dismissals showed the suppressed
row on the run page and hid it everywhere else.
"""
from __future__ import annotations

import pytest

from quodeq.api.app import create_app
from tests.perf._budget_fixture import PROJECT as PLAIN_PROJECT, seed_project
from tests.perf._golden_fixture import LATEST_RUN_ID, PROJECT, SUPPRESSION_RULE, seed_golden_project

_RUN = LATEST_RUN_ID
_EVAL = f"/api/projects/{PROJECT}/runs/{_RUN}/dimensions/security/eval"
_DETAIL = f"/api/projects/{PROJECT}/compliance-detail?dimension=security&kind=violation&run={_RUN}"
_SCORES = f"/api/projects/{PROJECT}/scores/{_RUN}"


def _identities(rows: list[dict]) -> set[tuple]:
    """The UI's merge key; it joins the fields as strings, so None and '' are one."""
    return {
        tuple(r.get(k) or "" for k in ("file", "line", "endLine", "practiceId", "title")) for r in rows
    }


def _ui_merge_keys(rows: list[dict]) -> list[str]:
    """``mergeFindingDetail``'s key, exactly: ``Array.join`` writes null as ''."""
    return ["\0".join("" if r.get(k) is None else str(r[k]) for k in ("file", "line", "endLine", "principle", "title"))
            for r in rows]


def _app(tmp_path, monkeypatch):
    monkeypatch.delenv("QUODEQ_API_KEY", raising=False)
    reports = tmp_path / "evaluations"
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(reports))
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "index.db"))
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "score_cache.db"))
    return reports


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """The golden project with only its pattern rule left as suppression state."""
    reports = _app(tmp_path, monkeypatch)
    seed_golden_project(reports)
    (reports / PROJECT / "actions.jsonl").unlink()
    (reports / PROJECT / "deleted.json").unlink()
    return create_app(static_dist=None, api_key=None).test_client()


def test_rules_only_project_lists_the_same_violations_on_every_run_route(client) -> None:
    eval_rows = client.get(_EVAL).get_json()["violations"]
    detail_rows = client.get(_DETAIL).get_json()["items"]
    scores = client.get(_SCORES).get_json()["dimensions"]
    scores_rows = next(d for d in scores if d["dimension"] == "security")["violations"]

    assert eval_rows, "the eval has violations"
    assert _identities(scores_rows) == _identities(eval_rows)
    assert _identities(detail_rows) == _identities(eval_rows)
    suppressed = [r for r in scores_rows + detail_rows + eval_rows if r.get("file") == "f7.py"]
    assert suppressed == [], f"rule {SUPPRESSION_RULE['req']} on {SUPPRESSION_RULE['file']} must hide the row"


@pytest.fixture()
def plain_client(tmp_path, monkeypatch):
    """A project with no suppression state at all: the SQL grade-tables path."""
    seed_project(_app(tmp_path, monkeypatch))
    return create_app(static_dist=None, api_key=None).test_client()


def test_eval_rows_refill_from_the_detail_route_on_the_sql_path(plain_client) -> None:
    """Rows read back from the run carry ``endLine`` and ``title``; rows parsed
    from the eval file do not. The eval must serve the run's rows, or the
    UI's merge key never matches and the detail stays deferred."""
    run = "20260103T000000"
    eval_rows = plain_client.get(f"/api/projects/{PLAIN_PROJECT}/runs/{run}/dimensions/security/eval").get_json()["violations"]
    detail_rows = plain_client.get(
        f"/api/projects/{PLAIN_PROJECT}/compliance-detail?dimension=security&kind=violation&run={run}").get_json()["items"]
    assert eval_rows and all(r["detailDeferred"] for r in eval_rows)
    assert sorted(_ui_merge_keys(eval_rows)) == sorted(_ui_merge_keys(detail_rows))
