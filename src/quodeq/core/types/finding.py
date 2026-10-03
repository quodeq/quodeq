"""The read-side finding view and the tallies reports aggregate it into."""
from __future__ import annotations

from dataclasses import dataclass, field

from quodeq.core.constants import FULL_CONFIDENCE
from quodeq.core.types.req_ref import ReqRef as ReqRef
from quodeq.core.types.severity import Severity


@dataclass(frozen=True, slots=True)
class SeverityTally:
    """Violation counts split by severity, with ``unknown`` for unrecognised labels."""

    critical: int = 0
    major: int = 0
    minor: int = 0
    unknown: int = 0


@dataclass(frozen=True, slots=True)
class Totals:
    """Headline counts for one dimension report, parsed by ``data.mappers.parse_totals``.

    ``violations_per100_files`` is None when the report did not record a
    source file count to normalise against.
    """

    violation_count: int = 0
    compliance_count: int = 0
    severity: SeverityTally = field(default_factory=SeverityTally)
    violations_per100_files: float | None = None


@dataclass(frozen=True, slots=True)
class Finding:
    """A judgment as every read surface sees it, after dismissal state is folded in.

    Projected from ``Judgment`` by ``core.finding_mappings.judgment_to_finding``.
    Nearly everything is optional because reports and databases written by
    older versions parse into this same shape. ``verdict`` may additionally be
    ``"dismissed"``, which the event log never stores -- it is derived from
    the user's dismissal actions at read time.
    """

    practice_id: str | None = None
    verdict: str | None = None  # "violation" | "compliance" | "dismissed"
    file: str | None = None
    line: int | str | None = None
    end_line: int | str | None = None
    title: str | None = None
    reason: str | None = None
    snippet: str | None = None
    severity: str = Severity.MINOR
    cwe: int | str | None = None
    req: str | None = None
    req_refs: list[ReqRef] = field(default_factory=list)
    context: str | None = None
    dimension: str | None = None
    violation_type: str | None = None
    violation_type_raw: str | None = None
    scope: str | None = None
    # 0..100. Default 100 means "scanner is fully sure this is real".
    # Lower values flag noise (path role, project shape, precedent) the
    # context-enricher pipeline downweights post-LLM.
    confidence: int = FULL_CONFIDENCE
    # True when the deterministic provenance gate (#639) de-escalated this
    # finding from critical to major. Audit marker surfaced in the DB/UI (#656).
    provenance_downgrade: bool = False
    # Set (dict: {"rule", "from", "to"}) when the deterministic scope gate
    # capped this finding's severity from major to minor per the declared
    # trust model. None when not gated. Unlike provenance_downgrade this is
    # a dict, not a bool: the marker exists to let a team later shipping as a
    # hosted service recover WHICH rule waived the finding, not just that
    # something did.
    scope_downgrade: dict[str, str] | None = None
    # True when this finding was replayed from the content-addressed cache
    # rather than produced by the running scan (see Judgment.carried_forward).
    carried_forward: bool = False
