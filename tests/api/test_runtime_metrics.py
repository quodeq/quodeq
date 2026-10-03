"""Runtime metrics: Server-Timing on responses, the debug endpoint, the log line."""
from __future__ import annotations

import re
import sys

import pytest

from quodeq.api.app import create_app
from quodeq.shared import request_metrics
from quodeq.shared.request_metrics import RequestRates
from quodeq.shared.stamp_memo import StampCache
from tests.perf._budget_fixture import PROJECT, seed_project

pytestmark = pytest.mark.real_standards

REMOTE = {"REMOTE_ADDR": "10.0.0.5"}
API_KEY = "k" * 40


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.delenv("QUODEQ_API_KEY", raising=False)
    reports = tmp_path / "evaluations"
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(reports))
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "index.db"))
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "score_cache.db"))
    seed_project(reports)
    return create_app(static_dist=None, api_key=None)


class TestServerTiming:
    def test_scores_carries_the_four_metrics(self, app):
        response = app.test_client().get(f"/api/projects/{PROJECT}/scores")
        assert response.status_code == 200
        header = response.headers["Server-Timing"]
        assert re.fullmatch(
            r'db;desc="\d+ opens", reads;desc="\d+ reports", build;dur=\d+\.\d, cache;desc="(hit|miss|none)"',
            header,
        ), header

    def test_cold_then_warm(self, app):
        client = app.test_client()
        cold = client.get(f"/api/projects/{PROJECT}/scores").headers["Server-Timing"]
        warm = client.get(f"/api/projects/{PROJECT}/scores").headers["Server-Timing"]
        assert 'cache;desc="miss"' in cold and 'db;desc="0 opens"' not in cold
        assert 'cache;desc="hit"' in warm and 'db;desc="0 opens"' in warm

    def test_scope_is_closed_after_the_request(self, app):
        app.test_client().get(f"/api/projects/{PROJECT}/scores")
        assert request_metrics.current() is None

    def test_log_line_carries_the_cost(self, app, caplog):
        with caplog.at_level("INFO", logger="quodeq.api.security"):
            app.test_client().get(f"/api/projects/{PROJECT}/scores")
        line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("API: GET"))
        assert re.search(r"-> 200 \[db=\d+ reads=\d+ build=\d+ms cache=(hit|miss|none)\]$", line), line


class TestDebugMetrics:
    def test_payload_shape(self, app):
        client = app.test_client()
        client.get(f"/api/projects/{PROJECT}/scores")
        body = client.get("/api/debug/metrics").get_json()
        rss = body["process"]["rss_bytes"]
        assert rss is None if sys.platform == "win32" else rss > 0
        assert body["process"]["cpu_user_s"] >= 0
        names = {cache["name"] for cache in body["caches"]}
        assert {"project_scores.payloads", "default"} <= names
        for cache in body["caches"]:
            assert set(cache) == {"name", "entries", "max_entries", "hits", "misses", "approx_bytes"}
        assert body["requests_last_minute"]["/api/projects/<project>/scores"] == 1

    def test_remote_caller_is_refused_even_with_a_key(self, tmp_path, monkeypatch):
        monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path / "evaluations"))
        monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "index.db"))
        client = create_app(static_dist=None, api_key=API_KEY).test_client()
        headers = {"Authorization": f"Bearer {API_KEY}"}
        assert client.get("/api/debug/metrics", headers=headers, environ_base=REMOTE).status_code == 403
        assert client.get("/api/debug/metrics", headers=headers).status_code == 200


class TestCounters:
    def test_count_is_a_no_op_outside_a_scope(self):
        assert request_metrics.current() is None
        request_metrics.count("db_opens")  # must not raise

    def test_cache_outcome(self):
        token = request_metrics.begin()
        try:
            metrics = request_metrics.current()
            assert metrics.cache_outcome == request_metrics.CACHE_NONE
            cache = StampCache(name="t")
            cache.get("k", (1,))
            cache.put("k", (1,), "v")
            assert metrics.cache_outcome == request_metrics.CACHE_MISS
            assert (metrics.cache_misses, metrics.cache_hits) == (1, 0)
            cache.get("k", (1,))
            assert metrics.cache_hits == 1
            assert (cache.hits, cache.misses) == (1, 1)
        finally:
            request_metrics.end(token)

    def test_cache_stats_estimate_size(self):
        cache = StampCache(name="sized", max_entries=10)
        for i in range(3):
            cache.put(f"k{i}", (i,), {"rows": list(range(100))})
        stats = cache.stats()
        assert stats["entries"] == 3
        assert stats["approx_bytes"] > 3 * 100 * 8


class TestRequestRates:
    def test_counts_inside_the_window_only(self):
        rates = RequestRates(window_s=60)
        rates.record("/a", now=0.0)
        rates.record("/a", now=30.0)
        rates.record("/b", now=59.0)
        assert rates.snapshot(now=61.0) == {"/a": 1, "/b": 1}
        assert rates.snapshot(now=200.0) == {}
