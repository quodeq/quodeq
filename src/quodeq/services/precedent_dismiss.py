"""Precedent auto-dismissal: a prior dismissal reaches the score (#1208).

A dismissal's identity is ``(req, file, snippet fingerprint)``, so a false
positive that recurs in the same file already leaves the score on the next
run. The precedent corpus also knows the same requirement and code in a
DIFFERENT file, but until now that match only lowered ``confidence``, a UI
signal scoring ignores on purpose (#640). Rather than teach scoring about
confidence, this records a real dismissal for the new occurrence: it leaves
the score through the seam every manual dismissal uses, shows in the
Dismissed tab with a reason that says why, and can be restored like any
other. A restore wins for good: code the user put back is never auto-dismissed
again until they dismiss it themselves (``restored_fingerprints``).

Only the exact fingerprint tier qualifies. A semantic match is a guess.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from quodeq.core.dismissals import DismissedKeys, restored_fingerprints
from quodeq.core.events.models import FindingDismissed, FindingDismissedEvent
from quodeq.core.finding_identity import coerce_line, snippet_fingerprint
from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.data.actions_log import ActionLogWriter, read_action_events
from quodeq.data.ports.actions_log import ActionLog
from quodeq.services.dismissed import dismissed_keys

PRECEDENT_REASON = "Precedent: same requirement and code as a finding you dismissed."


class PrecedentAutoDismisser:
    """Records one dismissal per ``(req, file, fingerprint)`` for exact precedent matches.

    The project's dismissed state and restored set are read once at
    construction: a run records at most a handful of these, and every seam
    that reads dismissals folds the log itself. A sibling process recording
    the same key writes a duplicate event, which the fold nets to one entry.
    """

    def __init__(self, project_dir: Path, *, writer: ActionLog | None = None) -> None:
        self._state: DismissedKeys = dismissed_keys(project_dir)
        self._restored = restored_fingerprints(read_action_events(project_dir))
        self._recorded: set[tuple[str, str, str]] = set()
        self._log: ActionLog = writer or ActionLogWriter(project_dir)

    def record(self, finding: dict) -> bool:
        """Dismiss *finding* on precedent. True when an event was written."""
        if finding.get("t") != "violation":
            return False
        req = str(finding.get("req") or "")
        file = str(finding.get("file") or "")
        snippet = finding.get("snippet")
        fp = snippet_fingerprint(req, snippet if isinstance(snippet, str) else None)
        if fp is None or (req, fp) in self._restored:
            return False
        line = coerce_line(finding.get("line"))
        if (req, file, fp) in self._recorded:
            return False
        if self._state.matches(req=req, file=file, line=line, snippet=snippet):
            return False
        self._log.emit(FindingDismissedEvent(payload=FindingDismissed(
            req=req, file=file, line=line, reason=PRECEDENT_REASON, fingerprint=fp,
        )))
        self._recorded.add((req, file, fp))
        return True


def precedent_match_hook(
    project_dir: Path | None, *, log: LogSink = NULL_LOG,
) -> Callable[[dict], None] | None:
    """The ``CompiledContext.on_precedent_match`` hook for *project_dir*, or None.

    None when there is no project directory (nowhere to record) or its
    action log cannot be read: precedent then stays a confidence-only signal
    for this run, which is what it was before #1208, and the scan proceeds.
    """
    if project_dir is None:
        return None
    try:
        return PrecedentAutoDismisser(project_dir).record
    except (OSError, ValueError) as exc:
        log.warning(f"Precedent auto-dismiss disabled for {project_dir}: {exc}")
        return None
