"""Post-loop and mid-loop health guards: dead-provider, zero-findings, unreachable-model."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.analysis.errors import EvaluationError, FatalProviderError
from quodeq.core.evidence.model import Evidence
from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.shared import cancellation


def _count_ok_files(run_dir: Path | None) -> int:
    """Files successfully analysed by THIS run's workers, across all dims.

    ``ok`` file_done markers are written only by dispatch workers; cache
    replays write findings without markers. So this count measures fresh
    progress this run made, never carried-forward data.
    """
    if run_dir is None:
        return 0
    evidence_dir = Path(run_dir) / "evidence"
    if not evidence_dir.is_dir():
        return 0
    total = 0
    for jsonl in evidence_dir.glob("*_evidence.jsonl"):
        ok, _err = _tally_markers(jsonl)
        total += ok
    return total


def _raise_on_fatal_cancel(run_dir: Path | None, *, log: LogSink = NULL_LOG) -> None:
    """Fail the run loudly when a dead provider stopped it before ANY analysis.

    Two outcomes, keyed on whether this run already analysed files
    successfully (``ok`` markers, see ``_count_ok_files``):

    - No successful analysis: the run is worthless. Raise so the lifecycle
      maps it to a failed run with a distinct exit_reason, instead of DONE
      with silently incomplete dimensions.
    - Partial success (e.g. quota died halfway): the data is worth keeping.
      Return without raising so the run finalizes as done; the CLI hook
      (``_record_provider_fatal_if_cancelled``) stamps the exit_reason so
      the UI says "stopped early, results are partial" rather than showing
      a clean completion.
    """
    reason = cancellation.cancel_reason() or ""
    is_provider_fatal = reason.startswith("provider_fatal")
    is_streak = reason == "agent_failure_streak"
    if not (is_provider_fatal or is_streak):
        return
    ok_files = _count_ok_files(run_dir)
    if ok_files > 0:
        log.warning(
            f"[loop] provider failed mid-run after {ok_files} file(s) were "
            f"analysed -- keeping partial results, run finalizes as done "
            f"with a stopped-early warning"
        )
        return
    if is_provider_fatal:
        raise FatalProviderError(
            f"evaluation aborted: {reason.partition(':')[2].strip() or 'fatal provider error'}",
            reason="provider_fatal",
        )
    from quodeq.analysis.cache._failure_streak import CircuitBreakerError
    raise CircuitBreakerError("agent_failure_streak")


def check_zero_findings(
    result: dict[str, Evidence], source_file_count: int, skipped_count: int = 0,
    *, incremental_filter_active: bool = False,
) -> None:
    """Raise EvaluationError if all dimensions produced zero findings.

    When *incremental_filter_active* is True, zero findings is a legitimate
    outcome (PR-diff / incremental mode deliberately narrows the scan to a
    changed-file set that may contain none of the dimension's language) -
    skip the check. Otherwise a genuinely empty result is almost always a
    symptom of a broken AI CLI tool loop, not a clean codebase.
    """
    if not result or source_file_count <= 0 or incremental_filter_active:
        return
    if _count_findings(result) == 0:
        skip_msg = f" ({skipped_count} skipped)" if skipped_count else ""
        raise EvaluationError(
            f"Evaluation produced 0 findings across {len(result)} dimensions{skip_msg}. "
            f"This usually means the AI CLI could not read files or report findings "
            "- check tool permissions and MCP configuration."
        )


def _count_findings(result: dict[str, Evidence]) -> int:
    """Total violations + compliance findings across all dimension Evidence.

    Counts findings carried forward from cache as well as freshly produced
    ones -- both land in ``Evidence.principles`` for the dims in ``result``.
    """
    return sum(
        sum(len(pe.violations) + len(pe.compliance) for pe in ev.principles.values())
        for ev in result.values()
    )


def _tally_markers(jsonl_path: Path) -> tuple[int, int]:
    """Return ``(ok_count, error_count)`` from a dim's evidence JSONL.

    Counts each file once by its *latest* ``file_done`` marker status, matching
    the cache's ok_files semantics (a file that errored then re-succeeded counts
    as ok). Unreadable/missing files contribute nothing.
    """
    last_status: dict[str, str] = {}
    try:
        # errors="replace" so a corrupt (non-UTF8) evidence file degrades to
        # unparseable lines (dropped by the json.loads guard) instead of
        # raising UnicodeDecodeError out of an otherwise-successful run.
        with jsonl_path.open("r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    entry = json.loads(raw)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if entry.get("_marker") != "file_done":
                    continue
                file = entry.get("file")
                status = entry.get("status")
                if isinstance(file, str) and status in ("ok", "error"):
                    last_status[file] = status
    except (FileNotFoundError, OSError):
        return 0, 0
    ok = sum(1 for s in last_status.values() if s == "ok")
    err = sum(1 for s in last_status.values() if s == "error")
    return ok, err


def check_model_reachable(run_dir: Path | None, result: dict) -> None:
    """Raise EvaluationError if the run attempted analysis but produced nothing.

    Fires only when ALL of the following hold, so it flags a genuinely worthless
    run (an unreachable/misconfigured model) without false-positiving on healthy
    or partial runs:

    - the run produced zero findings (fresh OR carried forward from cache). Any
      finding means real output exists, so a mostly-cached run is not failed just
      because the model blipped on the uncached remainder. (A lossy call now
      writes ``error`` markers, so the dim yields an *empty* Evidence rather than
      being skipped -- hence we gate on findings, not on ``result`` emptiness.)
    - zero files were successfully analysed (no ``ok`` file_done markers); and
    - at least one file was dispatched and failed (an ``error`` marker exists).

    Runs in every mode, including diff (review) and incremental (nightly) where
    ``check_zero_findings`` is deliberately bypassed -- those are exactly the
    modes where an unreachable model used to exit 0 (green) while producing
    nothing. A legitimately empty scan (no applicable files dispatched -> no
    markers) does not raise.

    Coverage note: the guard keys off file_done ``error`` markers. The Ollama /
    API provider path writes those on a lossy call (``run_api_analysis``), so the
    Ollama-backed CI flows are covered. A CLI provider (claude/gemini/codex) that
    is itself unreachable never connects to the MCP server and writes no markers
    at all, so this guard cannot see that failure in diff/incremental mode --
    that remains a known gap, out of scope for the Ollama incident this targets.
    """
    if run_dir is None or _count_findings(result) > 0:
        return
    evidence_dir = run_dir / "evidence"
    if not evidence_dir.is_dir():
        return
    ok_total = 0
    err_total = 0
    for jsonl in evidence_dir.glob("*_evidence.jsonl"):
        ok, err = _tally_markers(jsonl)
        ok_total += ok
        err_total += err
    if ok_total == 0 and err_total > 0:
        raise EvaluationError(
            f"Model produced no analysis: all {err_total} dispatched file(s) failed "
            f"and 0 were analysed. The model is likely unreachable or misconfigured "
            f"(check the provider/model name and that the server is running, "
            f"e.g. `ollama list`), or every dispatched file errored during analysis."
        )
