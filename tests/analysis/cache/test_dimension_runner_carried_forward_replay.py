"""Cache replays must be distinguishable from this scan's own findings.

Split from test_dimension_runner_carried_forward.py: the integration
tests that drive replay through ``process_dimension_with_cache`` (cache
hit vs. dispatch, unconsolidated hits, the sidecar, and the cancelled-run
user story). The direct unit tests for ``_write_findings`` /
``_emit_cached_findings`` live in test_dimension_runner_carried_forward_write.py.
"""
import json
from pathlib import Path

from quodeq.analysis.cache.dimension_helpers import build_cache_key_for_file
from quodeq.analysis.cache.dimension_runner import process_dimension_with_cache
from quodeq.analysis.cache.entry import CacheEntry
from tests.analysis.cache.conftest import (
    _make_callbacks,
    _make_ctx,
    _make_dummy_evidence,
    _setup,
)


def _finding(title: str) -> dict:
    return {
        "file": "a.py", "line": 1, "t": "violation", "w": title,
        "p": "P1", "d": "security", "req": "X-1", "severity": "minor",
        "snippet": "x", "reason": "r",
    }


def test_only_cache_replays_are_flagged(tmp_path: Path, cache):
    """a.py is a cache hit, b.py is dispatched. Exactly one is flagged."""

    config, _src = _setup(tmp_path, {"a.py": "x", "b.py": "y"})

    key = build_cache_key_for_file(config, "a.py", "security")
    cache.put(key, CacheEntry(
        key=key, schema_version=1,
        findings=[dict(_finding("carry-a"), file="a.py")],
        files_read=1, file_path="a.py", dimension="security",
        model_id="test-model",
    ))

    def fake_dispatch(cfg, dim_id, idx, ctx, callbacks, **_):
        jsonl = (cfg.work_dir or cfg.src) / f"{dim_id}_evidence.jsonl"
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        with jsonl.open("a") as out:
            out.write(json.dumps(dict(_finding("fresh-b"), file="b.py", p="P2")) + "\n")
            out.write(json.dumps({"_marker": "file_done", "file": "b.py", "status": "ok"}) + "\n")
        return _make_dummy_evidence(files_read=1)

    process_dimension_with_cache(
        config, "security", 1, _make_ctx(), _make_callbacks(), cache=cache,
        dispatcher=fake_dispatch,
    )

    jsonl_path = (config.work_dir or config.src) / "security_evidence.jsonl"
    lines = [json.loads(ln) for ln in jsonl_path.read_text().splitlines() if ln.strip()]
    by_title = {ln["w"]: ln for ln in lines if "_marker" not in ln}
    assert by_title["carry-a"].get("carried_forward") is True
    assert by_title["fresh-b"].get("carried_forward", False) is False


def test_all_unconsolidated_hits_are_still_written(tmp_path: Path, cache):
    """Two truthiness guards used to test classify.cached_findings to decide
    whether to write anything. Splitting the list makes both false when every
    hit is unconsolidated, which would silently DROP those findings from the
    run rather than merely mis-flagging them."""

    config, _src = _setup(tmp_path, {"a.py": "x", "b.py": "y"})

    key = build_cache_key_for_file(config, "a.py", "security")
    cache.put(key, CacheEntry(
        key=key, schema_version=1,
        findings=[dict(_finding("pending-a"), file="a.py")],
        files_read=1, file_path="a.py", dimension="security",
        model_id="test-model", consolidated=False,
    ))

    def fake_dispatch(cfg, dim_id, idx, ctx, callbacks, **_):
        jsonl = (cfg.work_dir or cfg.src) / f"{dim_id}_evidence.jsonl"
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        with jsonl.open("a") as out:
            out.write(json.dumps(dict(_finding("fresh-b"), file="b.py", p="P2")) + "\n")
            out.write(json.dumps({"_marker": "file_done", "file": "b.py", "status": "ok"}) + "\n")
        return _make_dummy_evidence(files_read=1)

    process_dimension_with_cache(
        config, "security", 1, _make_ctx(), _make_callbacks(), cache=cache,
        dispatcher=fake_dispatch,
    )

    jsonl_path = (config.work_dir or config.src) / "security_evidence.jsonl"
    lines = [json.loads(ln) for ln in jsonl_path.read_text().splitlines() if ln.strip()]
    titles = {ln["w"] for ln in lines if "_marker" not in ln}
    assert "pending-a" in titles, "unconsolidated hit was dropped from the run"


def test_salvage_path_keeps_unconsolidated_hits_when_dispatch_returns_none(
    tmp_path: Path, cache,
):
    """The ``miss_evidence is None`` salvage branch has its own truthiness
    guard (``replayed_anything``). Like the pre-dispatch write guard above,
    it used to test only ``classify.cached_findings``, so a dimension whose
    every hit is unconsolidated would compute ``replayed_anything=False`` and
    return None -- discarding an unconsolidated finding that was already
    sitting in the JSONL."""

    config, _src = _setup(tmp_path, {"a.py": "x", "b.py": "y"})

    key = build_cache_key_for_file(config, "a.py", "security")
    cache.put(key, CacheEntry(
        key=key, schema_version=1,
        findings=[dict(_finding("pending-a"), file="a.py")],
        files_read=1, file_path="a.py", dimension="security",
        model_id="test-model", consolidated=False,
    ))
    # b.py has no cache entry, so it lands in classify.misses and dispatch is
    # actually attempted (and not the all-hits short-circuit above).

    def fake_dispatch(cfg, dim_id, idx, ctx, callbacks, **_):
        return None

    evidence = process_dimension_with_cache(
        config, "security", 1, _make_ctx(), _make_callbacks(), cache=cache,
        dispatcher=fake_dispatch,
    )

    assert evidence is not None, (
        "salvage-path guard dropped an all-unconsolidated dimension's findings"
    )
    jsonl_path = (config.work_dir or config.src) / "security_evidence.jsonl"
    lines = [json.loads(ln) for ln in jsonl_path.read_text().splitlines() if ln.strip()]
    titles = {ln["w"] for ln in lines if "_marker" not in ln}
    assert "pending-a" in titles, "unconsolidated hit was dropped from the run"


def test_three_way_split_carried_pending_and_fresh(tmp_path: Path, cache):
    """The headline case: a consolidated hit is carried, an unconsolidated hit
    is not, and a dispatched finding is not."""

    config, _src = _setup(tmp_path, {"a.py": "x", "b.py": "y", "c.py": "z"})

    for name, title, consolidated in (
        ("a.py", "carry-a", True),
        ("b.py", "pending-b", False),
    ):
        key = build_cache_key_for_file(config, name, "security")
        cache.put(key, CacheEntry(
            key=key, schema_version=1,
            findings=[dict(_finding(title), file=name)],
            files_read=1, file_path=name, dimension="security",
            model_id="test-model", consolidated=consolidated,
        ))

    def fake_dispatch(cfg, dim_id, idx, ctx, callbacks, **_):
        jsonl = (cfg.work_dir or cfg.src) / f"{dim_id}_evidence.jsonl"
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        with jsonl.open("a") as out:
            out.write(json.dumps(dict(_finding("fresh-c"), file="c.py", p="P2")) + "\n")
            out.write(json.dumps({"_marker": "file_done", "file": "c.py", "status": "ok"}) + "\n")
        return _make_dummy_evidence(files_read=1)

    process_dimension_with_cache(
        config, "security", 1, _make_ctx(), _make_callbacks(), cache=cache,
        dispatcher=fake_dispatch,
    )

    jsonl_path = (config.work_dir or config.src) / "security_evidence.jsonl"
    lines = [json.loads(ln) for ln in jsonl_path.read_text().splitlines() if ln.strip()]
    by_title = {ln["w"]: ln for ln in lines if "_marker" not in ln}
    assert by_title["carry-a"].get("carried_forward") is True
    assert by_title["pending-b"].get("carried_forward", False) is False
    assert by_title["fresh-c"].get("carried_forward", False) is False


def test_replayed_unconsolidated_keys_sidecar_is_written_on_the_all_hits_path(
    tmp_path: Path, cache,
):
    """A fully cached dimension dispatches nothing, so it writes no
    dispatch_keys sidecar. Without this one it would never flip its entries
    and its findings would replay as new forever."""

    config, _src = _setup(tmp_path, {"a.py": "x"})

    key = build_cache_key_for_file(config, "a.py", "security")
    cache.put(key, CacheEntry(
        key=key, schema_version=1,
        findings=[dict(_finding("pending-a"), file="a.py")],
        files_read=1, file_path="a.py", dimension="security",
        model_id="test-model", consolidated=False,
    ))

    process_dimension_with_cache(
        config, "security", 1, _make_ctx(), _make_callbacks(), cache=cache,
    )

    sidecar = (config.work_dir or config.src) / "security_replayed_unconsolidated_keys.json"
    assert sidecar.is_file()
    assert json.loads(sidecar.read_text()) == {"a.py": key}


def test_no_sidecar_when_every_hit_is_already_consolidated(tmp_path: Path, cache):

    config, _src = _setup(tmp_path, {"a.py": "x"})

    key = build_cache_key_for_file(config, "a.py", "security")
    cache.put(key, CacheEntry(
        key=key, schema_version=1,
        findings=[dict(_finding("carry-a"), file="a.py")],
        files_read=1, file_path="a.py", dimension="security",
        model_id="test-model", consolidated=True,
    ))

    process_dimension_with_cache(
        config, "security", 1, _make_ctx(), _make_callbacks(), cache=cache,
    )

    sidecar = (config.work_dir or config.src) / "security_replayed_unconsolidated_keys.json"
    assert not sidecar.exists()


def test_cancelled_run_findings_stay_new_until_a_run_completes(tmp_path: Path):
    """The user story.

    Run 1 is cancelled with "keep findings", so its findings never reach an
    Overview. Run 2 replays them: they must read as THIS scan's findings,
    because the user has still never been shown them consolidated. Run 2
    completes, which consolidates them. Run 3 replays them as carried.
    """
    from quodeq.analysis.cache.consolidation import mark_run_consolidated
    from quodeq.analysis.cache.local import LocalFileBackend
    from tests.analysis.cache.conftest import _make_config

    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("x")
    shared_cache = LocalFileBackend(root=tmp_path / "cache")

    def _run_config(run_id: str):
        """A config whose work_dir IS <run_dir>/evidence, so the sidecars land
        where mark_run_consolidated looks for them."""
        run_dir = tmp_path / "reports" / "proj" / run_id
        (run_dir / "evidence").mkdir(parents=True, exist_ok=True)
        return _make_config(
            src, work_dir=run_dir / "evidence", file_names=["a.py"],
        ), run_dir

    def fake_dispatch(cfg, dim_id, idx, ctx, callbacks, **_):
        jsonl = (cfg.work_dir or cfg.src) / f"{dim_id}_evidence.jsonl"
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        with jsonl.open("a") as out:
            out.write(json.dumps(dict(_finding("found-a"), file="a.py")) + "\n")
            out.write(json.dumps({"_marker": "file_done", "file": "a.py", "status": "ok"}) + "\n")
        return _make_dummy_evidence(files_read=1)

    def _titles_with_flag(config) -> dict:
        jsonl = (config.work_dir or config.src) / "security_evidence.jsonl"
        lines = [json.loads(ln) for ln in jsonl.read_text().splitlines() if ln.strip()]
        return {
            ln["w"]: ln.get("carried_forward", False)
            for ln in lines if "_marker" not in ln
        }

    # Run 1: dispatches a.py, then the user cancels with "keep findings".
    # A cancelled run never calls mark_run_consolidated.
    config1, run_dir1 = _run_config("run1")
    process_dimension_with_cache(
        config1, "security", 1, _make_ctx(), _make_callbacks(), cache=shared_cache,
        dispatcher=fake_dispatch,
    )
    (run_dir1 / "status.json").write_text(json.dumps({"state": "cancelled"}))
    mark_run_consolidated(run_dir1, shared_cache)  # no-op: not done

    # Run 2: a.py is now a cache hit, but an UNCONSOLIDATED one.
    config2, run_dir2 = _run_config("run2")
    process_dimension_with_cache(
        config2, "security", 1, _make_ctx(), _make_callbacks(), cache=shared_cache,
    )
    assert _titles_with_flag(config2) == {"found-a": False}, (
        "a cancelled run's findings must still read as new"
    )

    # Run 2 completes, which consolidates the entry it replayed.
    (run_dir2 / "status.json").write_text(json.dumps({"state": "done"}))
    mark_run_consolidated(run_dir2, shared_cache)

    # Run 3: the same hit now reads as carried forward.
    config3, _run_dir3 = _run_config("run3")
    process_dimension_with_cache(
        config3, "security", 1, _make_ctx(), _make_callbacks(), cache=shared_cache,
    )
    assert _titles_with_flag(config3) == {"found-a": True}, (
        "a completed run consolidated these findings; they are carried now"
    )
