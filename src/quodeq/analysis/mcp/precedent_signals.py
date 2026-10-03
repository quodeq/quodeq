"""The already-dismissed findings a findings router downweights against."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from quodeq.config.context_env import precedent_settings
from quodeq.context.precedent import load_precedent_corpus, load_precedent_fingerprints
from quodeq.context.precedent_fingerprint import PrecedentMemo
from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.data.sqlite.findings_queries import (
    dismissed_source_stamp,
    read_dismissed_snippets_strict,
)
from quodeq.services.precedent_dismiss import precedent_match_hook
from quodeq.shared.constants import EVIDENCE_DIRNAME
from quodeq.shared.json_state import dump_json_and_replace
from quodeq.shared.lru import LRUDict

# Every agent of a run is its own findings-server process, so the in-process
# per-run memo starts empty each time and each spawn opened every past run's
# evaluation.db. The first spawn of a run leaves the union and the stamps it
# was read under here; later spawns reuse it while every stamp still matches.
PRECEDENT_SNAPSHOT_FILENAME = "precedent_fingerprints.json"
_READ_MEMO_MAX_RUNS = 4096  # one entry per run read in this spawn


def _run_stamps(project_dir: Path) -> dict[str, list[int]]:
    stamps: dict[str, list[int]] = {}
    for run in project_dir.iterdir():
        if run.is_dir() and (stamp := dismissed_source_stamp(run)) is not None:
            stamps[run.name] = list(stamp)
    return stamps


def _read_snapshot(path: Path, stamps: dict[str, list[int]]) -> set[str] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("stamps") != stamps:
        return None
    fps = data.get("fingerprints")
    return set(fps) if isinstance(fps, list) else None


def _write_snapshot(path: Path, stamps: dict[str, list[int]], fps: set[str], log: LogSink) -> None:
    try:
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        dump_json_and_replace(fd, tmp, path, {"stamps": stamps, "fingerprints": sorted(fps)})
    except OSError as exc:
        log.debug(f"precedent snapshot not written to {path}: {exc}")


def _precedent_fingerprints(project_dir: Path, run_dir: Path | None, log: LogSink) -> set[str]:
    """The project's precedent fingerprints, through the run's on-disk snapshot."""
    read: PrecedentMemo = LRUDict(_READ_MEMO_MAX_RUNS)

    def load() -> set[str]:
        return load_precedent_fingerprints(
            project_dir, read_dismissed=read_dismissed_snippets_strict,
            source_stamp=dismissed_source_stamp, cache=read,
        )
    snapshot_dir = run_dir / EVIDENCE_DIRNAME if run_dir else None
    if snapshot_dir is None or not snapshot_dir.is_dir() or not project_dir.is_dir():
        return load()
    path = snapshot_dir / PRECEDENT_SNAPSHOT_FILENAME
    # Stamps first: a dismissal landing during the load changes a stamp, so
    # the next spawn misses and reads again instead of trusting a stale union.
    stamps = _run_stamps(project_dir)
    if (hit := _read_snapshot(path, stamps)) is not None:
        return hit
    fps = load()
    # A run whose read failed (a locked DB) is skipped, not memoized; leaving
    # it out of a snapshot that records its stamp would hide its precedents.
    if all(Path(project_dir / name) in read for name in stamps):
        _write_snapshot(path, stamps, fps, log)
    return fps


def precedent_signals(
    project_dir: Path | None, run_dir: Path | None, *, log: LogSink = NULL_LOG,
) -> dict[str, object]:
    """The ``CompiledContext`` precedent fields for *project_dir* and *run_dir*.

    Without a project there are no dismissals and no corpus; without a run
    directory there is no corpus. The strict reader raises on a failed open,
    so the per-run memo skips the run instead of remembering it as having no
    dismissals. The corpus reads its settings from this process's env.
    *log* receives the auto-dismiss hook's warnings.
    """
    if not project_dir:
        return {"precedent_fingerprints": set(), "precedent_corpus": None,
                "on_precedent_match": precedent_match_hook(None, log=log)}
    return {
        "precedent_fingerprints": _precedent_fingerprints(project_dir, run_dir, log),
        "precedent_corpus": (
            load_precedent_corpus(project_dir, run_dir, settings=precedent_settings()) if run_dir else None),
        "on_precedent_match": precedent_match_hook(project_dir, log=log),
    }
