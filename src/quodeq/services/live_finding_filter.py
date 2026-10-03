"""Which judgments the live feed gets to see.

The run event log (``events.jsonl``) is an audit trail: every judgment the
model made lands there, passing checks included, and the cache replay
mirrors its cached rows into it too. The Evaluate screen's feed is a list
of violations. Forwarding the log as-is made a dimension with 42 violations
show 417 rows, most of them compliance judgments wearing a severity badge.

One classifier, three views: the heartbeat line, the scan-progress counters
and this filter all run a finding through ``evidence_tally.classify_finding``,
so a ``finding`` frame is exactly a row the heartbeat counts as a violation:
not compliance, not a duplicate of one already sent on this stream, not a
principle outside the dimension's standard, not a finding the user already
dismissed or deleted.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from quodeq.config.paths import default_paths
from quodeq.core.evidence.req_mapping import PrincipleResolver, build_principle_resolver
from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.core.types.finding_type import FindingType
from quodeq.services.suppression import SuppressionMatcher, build_matcher, project_suppressions
from quodeq.services.wiring import classify_finding, read_req_to_principle_map


def _as_evidence_row(judgment: Any) -> dict:
    """A Judgment in the vocabulary the classifier and the suppression matcher read."""
    return {
        "t": getattr(judgment, "verdict", None),
        "req": getattr(judgment, "req", None),
        "p": getattr(judgment, "practice_id", None),
        "file": getattr(judgment, "file", None),
        "line": getattr(judgment, "line", None),
        "snippet": getattr(judgment, "snippet", None),
    }


class LiveFindingFilter:
    """Per-stream admission of judgments as live findings.

    Built once per SSE subscriber and threaded through its ticks: the dedup
    set is what the client has already been sent, so it has to live as long
    as the connection. Suppression state is project-scoped and can change
    mid-run (a dismiss from the dashboard), so :meth:`refresh` re-reads it;
    the stream calls it once per tick that carried new judgments.
    """

    def __init__(
        self, run_dir: Path, *,
        evaluators_dir: Path | None = None, compiled_dir: Path | None = None,
        log: LogSink = NULL_LOG,
    ) -> None:
        # Layout is <project>/<run>: dismissals and deletions are project-wide.
        self._project_dir = run_dir.parent
        self._log = log
        paths = default_paths()
        self._evaluators_dir = evaluators_dir if evaluators_dir is not None else paths.evaluators_dir
        self._compiled_dir = compiled_dir if compiled_dir is not None else paths.standards_dir / "compiled"
        self._seen: dict[str, set[tuple]] = {}
        self._resolvers: dict[str, PrincipleResolver] = {}
        self._matchers: dict[str, SuppressionMatcher] = {}
        self._suppressions: tuple | None = None

    def refresh(self) -> None:
        """Re-read the project's suppression stores; rebuild matchers when they changed.

        An unreadable store leaves the previous state in place (raw counts on
        a fresh filter), the same fallback the heartbeat uses: a corrupt
        actions.jsonl must not take the stream down.
        """
        try:
            current = project_suppressions(self._project_dir)
        except (OSError, ValueError) as exc:
            self._log.warning(f"suppression state unavailable, live findings stay raw: {exc}")
            return
        if current != self._suppressions:
            self._suppressions = current
            self._matchers.clear()

    def admits(self, judgment: Any) -> bool:
        """True when *judgment* is a violation this stream has not sent yet."""
        dimension = str(getattr(judgment, "dimension", "") or "")
        row = _as_evidence_row(judgment)
        kind = classify_finding(
            row, self._seen.setdefault(dimension, set()),
            suppressed=self._suppressed_for(dimension),
            resolver=self._resolver_for(dimension),
        )
        return kind == FindingType.VIOLATION

    def _resolver_for(self, dimension: str) -> PrincipleResolver:
        resolver = self._resolvers.get(dimension)
        if resolver is None:
            resolver = build_principle_resolver(
                dimension, self._evaluators_dir, self._compiled_dir,
                req_map_reader=read_req_to_principle_map,
            )
            self._resolvers[dimension] = resolver
        return resolver

    def _suppressed_for(self, dimension: str):
        if self._suppressions is None:
            self.refresh()
        if self._suppressions is None:
            return None
        matcher = self._matchers.get(dimension)
        if matcher is None:
            dismissed, deleted = self._suppressions
            matcher = build_matcher(dimension, dismissed, deleted, evaluators_dir=self._evaluators_dir)
            self._matchers[dimension] = matcher
        return matcher.is_suppressed if matcher.active else None
