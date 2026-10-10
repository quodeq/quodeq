"""The Overview routes' deferral to the warm-up engine.

At boot, or after an upgrade invalidated the score caches, the Overview of a
large project used to be built inline on the request path while the warm-up
thread rebuilt the same project beside it. The two shared one interpreter,
the build outlived the client's timeout, and every retry started the work a
second time. The routes now ask here first: while the engine still owes the
project, it jumps the queue and the client gets a pending body to poll on.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from quodeq.services import warmup as _warmup
from quodeq.services.warmup import WarmupEngine

_LAST_KNOWN_FIELDS = ("grade", "score", "files")


def summary_is_pending(reports_dir: str, project_id: str) -> bool:
    """True when the project's card summary is a cache miss the engine has yet to fill."""
    from quodeq.services.wiring import list_runs  # noqa: PLC0415
    from quodeq.services._fs_metadata import read_accumulated_summary  # noqa: PLC0415

    reports_root = Path(reports_dir)
    runs = list_runs(reports_root, project_id)
    if not runs:
        return False
    return read_accumulated_summary(reports_root, project_id, runs)[3]


def defer_to_warmup(
    reports_dir: str, project_id: str, *,
    engine: WarmupEngine | None = None,
    summary_pending: Callable[[str, str], bool] | None = None,
) -> dict | None:
    """The pending body an Overview route answers with while the engine still owes *project_id*.

    None means the route builds its payload inline, as it always did: the
    engine is not running, has finished with this project, or never queued
    it, or the project's caches are already warm (a queued project whose
    summary hits the cache is served now, not held behind the queue). The
    project is moved to the head of the queue either way, so the warm-up of
    the project on screen never waits for the rest.

    The project the worker is on right now is always deferred, without the
    probe: the worker fills the card summary first and the scores and
    Overview after, so a summary hit there says nothing about the rest, and
    building inline beside the worker is the contention this avoids.

    *engine* defaults to the process-wide one, resolved at call time so a
    swapped one is honoured; *summary_pending* is the cache probe. Both are
    injection seams for tests.
    """
    target = engine if engine is not None else _warmup.engine
    target.prioritise(project_id)
    if target.current() == project_id:
        return _pending_body(target, project_id)
    if not target.owes(project_id):
        return None
    probe = summary_pending if summary_pending is not None else summary_is_pending
    if not probe(reports_dir, project_id):
        return None
    return _pending_body(target, project_id)


def _pending_body(engine: WarmupEngine, project_id: str) -> dict:
    """The pending body, with the last known card summary when there is one.

    ``lastKnown`` is the grade, score and file count computed under the
    previous version, so the Overview can show that grade dimmed while the
    rebuild runs. Absent when the project was never summarised.
    """
    from quodeq.services.score_cache import read_last_project_summary_cached  # noqa: PLC0415

    body: dict = {"pending": True, "warmup": engine.snapshot()}
    last = read_last_project_summary_cached(project_id)
    if last is not None:
        body["lastKnown"] = {field: last.get(field) for field in _LAST_KNOWN_FIELDS}
    return body
