"""Cross-request reuse of per-run data in the accumulated (as-of) view.

Selecting a day on the Overview score-history chart issues
``get_project_scores(..., as_of=<run>)``, which walks every run from the
selected one backwards. Those run sets overlap almost entirely between two
neighbouring selections, so the per-run reads must survive across calls --
otherwise every newly-selected day re-hydrates the whole findings corpus and
the dimension cards visibly lag behind the click.

Only the runs that actually *win* a dimension slot need their full findings
bodies; the rest are needed only for their scores. These tests pin both
halves: the walk is served from a slim process-lived cache, and the answer is
byte-identical to the uncached computation.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.services import accumulated as acc_mod
from quodeq.services.accumulated import (
    AccumulatedCacheConfig,
    WalkCache,
    compute_accumulated,
    create_accumulated_cache,
)
from quodeq.services.wiring import DEFAULT_WALK_CACHE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_run(reports_root: Path, project: str, run_id: str, dims: dict[str, str]) -> None:
    """Write one run with *dims* mapping dimension name -> overall score.

    Each dimension carries a violation body so a full read is measurably
    heavier than the slim projection the walk needs.
    """
    run_dir = reports_root / project / run_id
    eval_dir = run_dir / "evaluation"
    eval_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    for dim_name, score in dims.items():
        (eval_dir / f"{dim_name}.json").write_text(json.dumps({
            "dimension": dim_name,
            "overallScore": score,
            "overallGrade": "B",
            "filesRead": 12,
            "principles": [],
            "violations": [{
                "principleId": "P1",
                "severity": "major",
                "file": f"src/{dim_name}.py",
                "line": 4,
                "description": f"body for {run_id}/{dim_name}",
            }],
            "compliance": [],
        }))
        (evidence_dir / f"{dim_name}_evidence.json").write_text(
            json.dumps({"dimension": dim_name, "discipline": "python"}))
    (evidence_dir / "manifest.json").write_text("{}")
    (run_dir / "scan.json").write_text("{}")


def _project_with_runs(tmp_path: Path, project: str, n: int) -> tuple[Path, list[str]]:
    """Build *n* runs, newest last in creation order. Returns (root, run_ids desc)."""
    reports_root = tmp_path / "evaluations"
    run_ids = [f"2026070{i}" if i < 10 else f"202607{i}" for i in range(10, 10 + n)]
    for i, run_id in enumerate(run_ids):
        _write_run(reports_root, project, run_id, {"security": f"{5 + (i % 4)}.0"})
    return reports_root, sorted(run_ids, reverse=True)


@pytest.fixture
def counting_reader(monkeypatch):
    """Count full ``read_run_data`` calls per run id, wrapping the real reader."""
    from quodeq.data.fs.report_parser import runs as runs_mod

    calls: list[str] = []
    real = runs_mod.read_run_data

    def _counted(reports_root, project, run_id):
        calls.append(run_id)
        return real(reports_root, project, run_id)

    monkeypatch.setattr("quodeq.services.cache.read_run_data", _counted)
    monkeypatch.setattr("quodeq.services._accumulated_data.read_run_data", _counted)
    return calls


@pytest.fixture(autouse=True)
def _clear_process_cache():
    """Isolate each test from the module-level cache."""
    acc_mod.clear_accumulated_process_cache()
    yield
    acc_mod.clear_accumulated_process_cache()


# ---------------------------------------------------------------------------
# Cross-call reuse
# ---------------------------------------------------------------------------

def test_slim_walk_read_failure_logs_and_the_run_is_skipped(tmp_path, recording_log, monkeypatch):
    """A single run's read_run_data failure during the slim classification
    walk must not abort the whole accumulated view -- it already degraded
    to skipping that run's dimensions; the walk must also say so."""
    from quodeq.data.fs.report_parser.runs import read_run_data as real_read_run_data

    root, runs_desc = _project_with_runs(tmp_path, "proj", 5)
    flaky_run = runs_desc[2]

    def _flaky(reports_root, project, run_id):
        if run_id == flaky_run:
            raise ValueError("corrupt eval file")
        return real_read_run_data(reports_root, project, run_id)

    monkeypatch.setattr("quodeq.services._accumulated_data.read_run_data", _flaky)

    result = compute_accumulated(str(root), "proj", runs_desc[0], log=recording_log)

    assert result is not None
    assert recording_log.warning_messages
    assert any(
        "read_run_data failed" in msg and flaky_run in msg
        for msg in recording_log.warning_messages
    )


def test_neighbouring_as_of_selections_reuse_the_run_walk(tmp_path, counting_reader):
    """The second day selected must not re-read every run's findings again.

    This is the regression under test: ``resolve_cache(None)`` used to build a
    fresh empty LRU per call, so each as-of selection re-hydrated the entire
    run history from disk.
    """
    root, runs_desc = _project_with_runs(tmp_path, "proj", 12)

    compute_accumulated(str(root), "proj", runs_desc[1])
    first_call_reads = len(counting_reader)
    counting_reader.clear()

    compute_accumulated(str(root), "proj", runs_desc[2])
    second_call_reads = len(counting_reader)

    # The two walks overlap in all but one run, so the second selection should
    # only pay for the dimension bodies it actually renders -- a small constant,
    # not another full sweep.
    assert first_call_reads >= 10, "fixture too small to be meaningful"
    assert second_call_reads <= 2, (
        f"second as-of selection re-read {second_call_reads} runs in full; "
        f"expected the walk to be served from the process cache"
    )


def test_repeat_selection_reads_only_the_winning_runs(tmp_path, counting_reader):
    """A repeat selection still hydrates the rendered dimensions.

    Those bodies are never cached in the process cache -- they are the megabyte
    half of a run read. What must not repeat is the walk over the other seven
    runs.
    """
    root, runs_desc = _project_with_runs(tmp_path, "proj", 8)

    compute_accumulated(str(root), "proj", runs_desc[1])
    counting_reader.clear()
    compute_accumulated(str(root), "proj", runs_desc[1])

    # One dimension in this fixture, so exactly one run owns a latest slot.
    assert len(set(counting_reader)) <= 1, (
        f"expected only the winning run to be re-read, got {sorted(set(counting_reader))}"
    )


# ---------------------------------------------------------------------------
# Correctness: the cache must not change the answer, and must not go stale
# ---------------------------------------------------------------------------

def test_cached_result_matches_uncached_computation(tmp_path):
    """Parity: a warm process cache yields the same payload as a cold one."""
    root, runs_desc = _project_with_runs(tmp_path, "proj", 10)

    # Cold: isolated per-call cache, nothing shared.
    cold = []
    for run_id in runs_desc[:5]:
        cache, lock = create_accumulated_cache()
        cold.append(compute_accumulated(
            str(root), "proj", run_id,
            cache_config=AccumulatedCacheConfig(cache=cache, cache_lock=lock, cache_max=256),
        ))

    acc_mod.clear_accumulated_process_cache()

    # Warm: the module-level cache carries over between selections.
    warm = [compute_accumulated(str(root), "proj", run_id) for run_id in runs_desc[:5]]

    assert warm == cold


def test_rewritten_run_invalidates_the_cached_entry(tmp_path):
    """A run's scores can change in place (dismiss, grade-formula apply).

    The process cache keys on a per-run fingerprint, so a rewritten run must be
    re-read rather than served from the previous computation.
    """
    root, runs_desc = _project_with_runs(tmp_path, "proj", 4)
    newest = runs_desc[0]

    before = compute_accumulated(str(root), "proj", newest)
    assert before["summary"]["numericAverage"] == pytest.approx(8.0)

    eval_file = root / "proj" / newest / "evaluation" / "security.json"
    data = json.loads(eval_file.read_text())
    data["overallScore"] = "2.0"
    eval_file.write_text(json.dumps(data))

    after = compute_accumulated(str(root), "proj", newest)
    assert after["summary"]["numericAverage"] == pytest.approx(2.0), (
        "cached entry survived a rewrite of the run's evaluation data"
    )


def test_explicit_cache_config_still_isolates(tmp_path, counting_reader):
    """Callers passing their own cache_config keep per-call isolation."""
    root, runs_desc = _project_with_runs(tmp_path, "proj", 6)

    for _ in range(2):
        cache, lock = create_accumulated_cache()
        compute_accumulated(
            str(root), "proj", runs_desc[1],
            cache_config=AccumulatedCacheConfig(cache=cache, cache_lock=lock, cache_max=256),
        )

    # Both calls did their own reads -- an explicitly supplied cache is not
    # silently promoted to the shared process cache.
    assert len(counting_reader) >= 8


# ---------------------------------------------------------------------------
# G3 process-scoped owner: one WalkCache instance shared by every request
# with no explicit cache_config (Review Focus 1).
# ---------------------------------------------------------------------------

def test_two_request_paths_share_the_default_walk_cache_instance(tmp_path):
    """Two independent compute_accumulated calls -- as two different request
    handlers would make them -- must observe the SAME process-wide WalkCache,
    not one each."""
    root, runs_desc = _project_with_runs(tmp_path, "proj", 6)
    assert len(DEFAULT_WALK_CACHE.cache) == 0, "walk cache must start empty for this test"

    compute_accumulated(str(root), "proj", runs_desc[0])
    populated_after_first = len(DEFAULT_WALK_CACHE.cache)
    assert populated_after_first > 0, "the walk must have populated the shared instance"

    # A second, independent call path reuses the same object rather than a
    # fresh one of its own.
    compute_accumulated(str(root), "proj", runs_desc[1])
    assert len(DEFAULT_WALK_CACHE.cache) >= populated_after_first


def test_walk_cache_max_size_is_re_read_on_every_call(monkeypatch):
    """WalkCache.max_size() must call max_fn() live, not snapshot it at
    construction time -- QUODEQ_ACC_WALK_CACHE_MAX has to take effect on the
    very next call, matching walk_cache_max()'s own contract."""
    cache = WalkCache(max_fn=acc_mod.walk_cache_max)
    monkeypatch.delenv("QUODEQ_ACC_WALK_CACHE_MAX", raising=False)
    assert cache.max_size() == 2048

    monkeypatch.setenv("QUODEQ_ACC_WALK_CACHE_MAX", "3")
    assert cache.max_size() == 3


def test_walk_cache_evicts_oldest_first_like_the_old_ordereddict(tmp_path):
    """Pin the walk cache's eviction order/size: FIFO on insert past the cap,
    and a hit refreshes recency -- identical to the old bare OrderedDict."""
    root, runs_desc = _project_with_runs(tmp_path, "proj", 3)
    fetch = acc_mod.make_slim_run_fetcher(root, "proj", DEFAULT_WALK_CACHE.cache, DEFAULT_WALK_CACHE.lock, 2)

    fetch(runs_desc[0])
    fetch(runs_desc[1])
    assert len(DEFAULT_WALK_CACHE.cache) == 2

    # A hit on the oldest entry refreshes it to most-recently-used.
    fetch(runs_desc[0])
    fetch(runs_desc[2])
    assert len(DEFAULT_WALK_CACHE.cache) == 2

    keys = list(DEFAULT_WALK_CACHE.cache.keys())
    surviving_runs = {key[2] for key in keys}
    assert surviving_runs == {runs_desc[0], runs_desc[2]}, (
        "the refreshed entry and the newest insert must survive; the untouched "
        "one must be the one evicted"
    )
