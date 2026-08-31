"""One place that decides whether a raw evidence row is suppressed.

Dismiss and delete use different identity keys, and those keys have drifted
from their consumers before (a dismiss filter matching on principle name
while the finding dicts carried practiceId, so the filter sat inert). Every
reader that has to answer "would the dashboard hide this finding?" should
build its keys here rather than re-deriving them:

- dismissed: ``(req, file, line)``           -- one finding, exact line
- deleted:   ``(dimension, principle, file)`` -- whole principle in a file

Evidence rows carry ``p`` (a req ID for custom evaluators, otherwise the
principle name) and optionally ``req``. The delete store carries principle
*names*, so ``p`` is mapped through the evaluator's req -> principle table
before the delete key is built -- the same order ``_parse_jsonl_findings``
applies when it builds the scored report.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from quodeq.config.paths import default_paths
from quodeq.services.deleted import deleted_keys
from quodeq.services.dismissed import dismissed_keys
from quodeq.services.suppression_keys import (  # noqa: F401 — re-exported API
    _coerce_line,
    is_deleted,
    is_dismissed,
)
from quodeq.shared.validation import validate_path_segment
from quodeq.services._wiring import (  # noqa: F401 — re-exported API
    load_suppression_rules,
)

_TYPE_VIOLATION = "violation"


@dataclass(frozen=True)
class SuppressionMatcher:
    """Immutable view of one dimension's suppression state."""

    dimension: str
    dismissed: frozenset = frozenset()
    deleted: frozenset = frozenset()
    rules: tuple = ()
    req_to_principle: Mapping[str, str] = field(default_factory=dict)

    @property
    def active(self) -> bool:
        """False when nothing is suppressed -- callers can skip the scan."""
        return bool(self.dismissed or self.deleted or self.rules)

    def principle_for(self, raw: str) -> str:
        """Map an evidence ``p`` (req ID or principle name) to a principle name."""
        return self.req_to_principle.get(raw, raw)

    def is_suppressed(self, row: dict) -> bool:
        """True when the dashboard would hide this raw evidence row.

        Compliance rows are never suppressed: both stores only ever record
        violations, and hiding a passing check would silently inflate the
        compliance ratio.
        """
        if not self.active or row.get("t") != _TYPE_VIOLATION:
            return False
        raw = row.get("p") or row.get("req")
        if not raw:
            return False
        file = row.get("file") or ""
        if is_dismissed(self.dismissed, req=row.get("req"), principle=raw,
                        file=file, line=row.get("line"), rules=self.rules):
            return True
        return is_deleted(self.deleted, dimension=self.dimension,
                          principle=self.principle_for(raw), file=file)


def load_req_to_principle(
    dimension: str, evaluators_dir: Path | None = None,
) -> dict[str, str]:
    """Load the req ID -> principle name mapping for a custom evaluator.

    Empty dict when the evaluator is absent or malformed: built-in dimensions
    already emit principle names in ``p``, so an empty map is the identity.
    """
    if evaluators_dir is None:
        evaluators_dir = default_paths().evaluators_dir
    if not evaluators_dir.is_dir():
        return {}
    validate_path_segment(dimension)
    path = evaluators_dir / f"{dimension}.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}  # valid JSON but not an object: degrade, don't crash
        mapping: dict[str, str] = {}
        for p in data.get("principles", []):
            pname = p.get("name", "")
            for req in p.get("requirements", []):
                rid = req.get("id", "")
                if rid and pname:
                    mapping[rid] = pname
        return mapping
    except (OSError, ValueError):
        return {}


def project_suppressions(project_dir: Path) -> tuple[frozenset, frozenset]:
    """Read a project's ``(dismissed, deleted)`` key sets.

    Read fresh on every call. The live-progress reader polls this once per
    tick, and a dismiss landing mid-scan has to show up on the next one -- a
    memo keyed on anything coarser than the file contents would freeze the
    counts for the rest of the run.
    """
    return frozenset(dismissed_keys(project_dir)), frozenset(deleted_keys(project_dir))


def build_matcher(
    dimension: str,
    dismissed: frozenset,
    deleted: frozenset,
    *,
    evaluators_dir: Path | None = None,
    rules: tuple = (),
) -> SuppressionMatcher:
    """Attach already-loaded key sets to one dimension.

    Split from :func:`matcher_for` so a caller iterating every dimension of a
    run (the progress reader) pays for the store reads once, not once per
    dimension.
    """
    if not dismissed and not deleted and not rules:
        # Nothing to map against, so skip the evaluator read entirely.
        return SuppressionMatcher(dimension=dimension)
    return SuppressionMatcher(
        dimension=dimension,
        dismissed=dismissed,
        deleted=deleted,
        rules=rules,
        req_to_principle=load_req_to_principle(dimension, evaluators_dir),
    )


def matcher_for(
    project_dir: Path, dimension: str, *, evaluators_dir: Path | None = None,
) -> SuppressionMatcher:
    """Build the matcher for *dimension* from *project_dir*'s suppression stores."""
    dismissed, deleted = project_suppressions(project_dir)
    return build_matcher(dimension, dismissed, deleted, evaluators_dir=evaluators_dir,
                         rules=load_suppression_rules(project_dir))
