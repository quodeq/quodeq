"""The respawn poll launches agents only for files no in-flight agent will take.

``scout_loop``/``immediate_loop`` used to spawn one agent per finished
future whenever any file was pending, re-reading the queue once per
finished future. Agents still in flight take from the same pending set, so
at the tail of every queue this launched agents that took an empty batch.
The poll now reads the queue once and launches
min(pending - in flight, slots just vacated).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quodeq.analysis.subagents._pool_loops import (
    LoopContext,
    immediate_loop,
    scout_loop,
)

_N_AGENTS = 5
_LOOPS = [
    pytest.param(scout_loop, id="scout"),
    pytest.param(immediate_loop, id="immediate"),
]


def _ctx(tmp_path: Path, **overrides) -> LoopContext:
    kwargs = dict(
        futures={object(): 0}, finished={}, results=[],
        max_duration=0.0, pool_start=0.0, n_agents=_N_AGENTS,
        queue=None, queue_path=tmp_path / "queue.json",
        shared_jsonl_path=tmp_path / "shared.jsonl",
        evidence_dir=tmp_path, dimension_key="security",
        submit_fn=MagicMock(), is_cancelled=lambda: False,
    )
    kwargs.update(overrides)
    return LoopContext(**kwargs)


class _ScriptedPolls:
    """collect_done stand-in. Each poll reports *done* finished futures and
    leaves *in_flight* placeholders in ctx.futures for the agents still
    running; once the script runs out, everything has finished."""

    def __init__(self, polls: list[tuple[int, int]]) -> None:
        self._polls = iter(polls)

    def __call__(self, futures, finished, results, paths) -> set:
        done, in_flight = next(self._polls, (0, 0))
        futures.clear()
        futures.update({object(): i for i in range(in_flight)})
        return {object() for _ in range(done)}


def _respawns(loop, ctx: LoopContext, *, done: int, in_flight: int, remaining: int) -> tuple[int, int]:
    """Run one respawn poll through *loop*: *done* agents finished, *in_flight*
    still run, the queue reports *remaining*. The scout gate is treated as
    already open (the burst is not under test here). Returns (agents
    respawned, queue reads made by the poll)."""
    polls = [(done, in_flight)]
    if loop is scout_loop:
        # The scout finishing opens the gate; that poll never respawns.
        polls.insert(0, (1, done + in_flight))
    launched = 1 if loop is scout_loop else ctx.n_agents
    should_respawn = MagicMock(return_value=remaining)
    with patch("quodeq.analysis.subagents._pool_loops.collect_done", _ScriptedPolls(polls)), \
         patch("quodeq.analysis.subagents._pool_loops.should_respawn", should_respawn), \
         patch("quodeq.analysis.subagents._pool_loops.maybe_scale_up", return_value=True), \
         patch("quodeq.analysis.subagents._pool_loops._FUTURE_POLL_INTERVAL_S", 0):
        loop(ctx)
    return ctx.submit_fn.call_count - launched, should_respawn.call_count


@pytest.mark.parametrize("loop", _LOOPS)
class TestRespawnBound:
    def test_in_flight_agents_cover_the_pending_files(self, loop, tmp_path):
        # Two agents still running, two files left: they will take them.
        respawned, _ = _respawns(loop, _ctx(tmp_path), done=1, in_flight=2, remaining=2)
        assert respawned == 0

    def test_two_finished_at_once_do_not_double_up_on_one_file(self, loop, tmp_path):
        respawned, _ = _respawns(loop, _ctx(tmp_path), done=2, in_flight=1, remaining=1)
        assert respawned == 0

    def test_surplus_files_refill_the_vacated_slot(self, loop, tmp_path):
        # Three left, one in flight: two files need an agent, one slot is free.
        respawned, _ = _respawns(loop, _ctx(tmp_path), done=1, in_flight=1, remaining=3)
        assert respawned == 1

    def test_respawn_is_capped_by_the_slots_just_vacated(self, loop, tmp_path):
        respawned, _ = _respawns(loop, _ctx(tmp_path), done=2, in_flight=0, remaining=5)
        assert respawned == 2

    def test_nothing_left_respawns_nothing(self, loop, tmp_path):
        # should_respawn reports 0 on cancel, deadline and pool time limit too.
        respawned, _ = _respawns(loop, _ctx(tmp_path), done=2, in_flight=0, remaining=0)
        assert respawned == 0

    def test_one_queue_read_per_poll(self, loop, tmp_path):
        _, reads = _respawns(loop, _ctx(tmp_path), done=3, in_flight=0, remaining=5)
        assert reads == 1
