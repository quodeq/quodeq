"""Cache-replay path: writing cached findings back into a run's evidence.

Split out of ``dimension_runner.py`` (B4/B5e/B6): everything here is about
turning cache entries (hits, consolidated or not) back into JSONL rows and
``events.jsonl`` entries, plus the small path helpers that path needs. The
dispatch/orchestration side (classify, watchers, breaker) stays in
``dimension_runner.py``.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

from quodeq.analysis._types import RunConfig
from quodeq.analysis.cache.dimension_helpers import ClassifyResult, _group_findings_by_file
from quodeq.analysis.mcp.severity_gates import apply_severity_gates
from quodeq.context.trust_model import TrustModel
from quodeq.data.ports.events import EventEmitter

_logger = logging.getLogger(__name__)


def _evidence_dir(config: RunConfig) -> Path:
    return config.work_dir or config.src


def _jsonl_path(config: RunConfig, dim_id: str) -> Path:
    return _evidence_dir(config) / f"{dim_id}_evidence.jsonl"


def _write_replayed_keys_sidecar(
    config: RunConfig, dim_id: str, keys: dict[str, str],
) -> None:
    """Record which unconsolidated cache entries this dim replayed.

    A run that reaches ``done`` consolidates not only the entries it wrote
    but the unconsolidated ones it replayed: those findings are now in a
    completed run's report. ``consolidation.mark_run_consolidated`` reads
    this sidecar alongside ``<dim>_dispatch_keys.json``.

    Skipped when there is nothing to record, so a run that replays only
    consolidated entries leaves no file behind.
    """
    if not keys:
        return
    sidecar = _evidence_dir(config) / f"{dim_id}_replayed_unconsolidated_keys.json"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(json.dumps(keys, indent=2), encoding="utf-8")


def _compute_files_read(
    classify: ClassifyResult, jsonl_path: Path, all_files: list[str],
) -> int:
    """Return the count of source files reproducible from the cache after
    this run ends.

    A source file is "reproducible" if either:
      - it was a cache hit (the file was replayed from a cache entry,
        consolidated or not — its cache entry already exists), or
      - it was dispatched and the worker emitted ``file_done="ok"``
        (which triggers a synchronous cache write via
        ``build_cache_writer``, or the watcher's next persist tick).

    Files with ``file_done="error"`` or no marker at all are NOT counted:
    their analysis was incomplete and the cache contains no entry for
    them, so the next run must re-dispatch.

    Pre-fix, ``files_read`` was set to ``len(input_files)`` at every
    callsite, making coverage % (computed downstream as
    ``files_read / source_file_count``) meaningless: it always read 100%
    even on deadline-truncated runs. The user reported a flexibility
    score of "6.6/Adequate" on a run that actually analyzed ~850/3037
    files — the dashboard couldn't tell it was partial.
    """
    n_hits = len(all_files) - len(classify.misses)
    if not jsonl_path.is_file():
        return n_hits
    _grouped, ok_files = _group_findings_by_file(jsonl_path)
    miss_set = set(classify.misses)
    n_dispatch_ok = len(ok_files & miss_set)
    return n_hits + n_dispatch_ok


def _events_log_path(jsonl: Path) -> Path:
    """Return the run's events.jsonl path given a per-dim evidence JSONL.

    Evidence files live at ``<run_dir>/evidence/<dim>_evidence.jsonl``; the
    event log lives at ``<run_dir>/events.jsonl``. Centralising the join so
    the two callers below can't drift apart.
    """
    return jsonl.parent.parent / "events.jsonl"


def _emit_cached_findings(
    events_log: Path, findings: list[dict], *,
    writer_factory: Callable[[Path], EventEmitter] | None = None,
) -> None:
    """Emit cached findings as JUDGMENT_CREATED events to the run's event log.

    Cached findings replayed by the V2 cache in incremental runs were
    landing only in the per-dim JSONL and never reaching ``events.jsonl``.
    The SQL projection runs off ``events.jsonl``, so the dashboard's grade
    tables saw only the freshly-dispatched findings and produced scores
    that disagreed with the CLI's JSON file (e.g. flexibility scoring 9.0
    in the UI vs 7.7 from the CLI on the same run). Mirroring each cached
    finding into the event log closes that gap.

    Exceptions are caught per finding and logged — the JSONL write
    already succeeded above, so an event-emit failure should not propagate
    and roll back the cache restore.
    """
    if not findings:
        return
    from quodeq.core.events.models import JudgmentCreatedEvent  # noqa: PLC0415
    from quodeq.core.finding_mappings import wire_dict_to_judgment  # noqa: PLC0415

    if writer_factory is None:
        # Lazy default resolution: the concrete data-layer writer is only
        # imported when no factory was injected.
        from quodeq.data.events.writer import EventLogWriter  # noqa: PLC0415
        writer_factory = EventLogWriter
    writer = writer_factory(events_log)
    for finding in findings:
        try:
            payload = wire_dict_to_judgment(finding)
            writer.emit(JudgmentCreatedEvent(payload=payload))
        except Exception:  # noqa: BLE001 — event-log emit must never break a cache replay
            _logger.warning(
                "cache replay: event emit failed for finding p=%r file=%r line=%r",
                finding.get("p"), finding.get("file"), finding.get("line"),
                exc_info=True,
            )


def _write_findings(
    jsonl: Path, findings: list[dict], *, append: bool,
    emit_events: bool = True,
    unconsolidated: list[dict] | None = None,
    trust_model: TrustModel | None = None,
    writer_factory: Callable[[Path], EventEmitter] | None = None,
) -> None:
    """Replay cached findings into this run's evidence JSONL.

    *findings* come from consolidated cache entries: a completed run already
    put them in its report and the user has seen them in an Overview. Those
    are stamped ``carried_forward`` so the live feed can hide them.

    *unconsolidated* come from entries no completed run has consolidated yet,
    because the run that produced them was cancelled with "keep findings",
    failed, or was killed. The user was never shown those in an Overview, so
    they are written verbatim and read as this scan's own findings.

    Both groups are re-gated and both are mirrored to events.jsonl. Skipping
    the unconsolidated group in the event log would resurrect the UI-vs-CLI
    score disagreement that _emit_cached_findings exists to prevent.
    """
    pending = list(unconsolidated or [])
    # Re-gate cached findings on the replay path (issue #657). The live
    # finding path gates in FindingEnricher.enrich(); cache replay bypasses
    # enrich(), so a stale, un-gated critical R-FT-2/S-AUT-3 finding written
    # by a pre-#639 quodeq version would otherwise replay at critical and
    # inflate the grade. The gate only touches un-gated criticals, so
    # re-gating an already-gated (or non-critical) finding is a no-op --
    # safe to apply unconditionally to every cached finding.
    #
    # The scope gate is re-applied here for the identical reason: it too
    # runs at the FindingEnricher sink (enrich(), after apply_provenance_gate),
    # which cache replay bypasses just like the provenance gate. CacheKey
    # deliberately does not fingerprint the declared trust model (that would
    # defeat the point of gating at replay time instead of at the cache key),
    # so a cached finding survives untouched across a
    # ``.quodeq/project-profile.json`` edit unless something re-gates it on
    # every replay -- this is that something. The practical effect: editing
    # the profile to declare, say, ``networkExposure: loopback`` re-caps
    # already-cached ``major`` findings on the very next run, without a cache
    # miss or a CacheKey change.
    #
    # apply_scope_gate is symmetric (see its own module docstring): the same
    # call also restores a finding this gate previously capped to ``minor``
    # once the profile is TIGHTENED enough that the rule that capped it no
    # longer fires. Without that other direction, a team that declares
    # loopback, scans, then honestly ships hosted and widens the profile back
    # to ``{"networkExposure": "public"}`` would see every already-cached
    # finding stay stuck at ``minor`` forever -- the exact same staleness
    # problem this whole re-gating pass exists to prevent, just in reverse.
    #
    # apply_severity_gates owns the sequence and the order it must run in
    # (see severity_gates.py); this call site owns only the decision to
    # re-gate on replay at all.
    for finding in findings:
        apply_severity_gates(finding, trust_model)
    for finding in pending:
        apply_severity_gates(finding, trust_model)
    # Every caller of this function is a cache replay -- the dispatcher
    # writes its own fresh findings and never comes through here. Stamp the
    # origin so the live evaluation feed can show only what this scan is
    # actually producing.
    #
    # Copy, do not mutate: these dicts are owned by the cache entries, and
    # the periodic-persist watcher could otherwise write the flag back into
    # the cache, making a later fresh scan of the same file look carried.
    #
    # Consolidated first, then unconsolidated, so the JSONL keeps reading
    # foundation-then-new.
    stamped = [{**finding, "carried_forward": True} for finding in findings]
    stamped += [dict(finding) for finding in pending]
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with jsonl.open(mode, encoding="utf-8") as out:
        for finding in stamped:
            out.write(json.dumps(finding) + "\n")
    if emit_events:
        _emit_cached_findings(
            _events_log_path(jsonl), stamped, writer_factory=writer_factory,
        )
