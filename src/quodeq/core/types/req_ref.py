"""The requirement back-reference carried by findings and judgments."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReqRef:
    """A link from a finding back to the requirement it was judged against.

    Built by ``core.finding_mappings._coerce_req_refs`` from whatever the
    model emitted, so both fields can be empty strings.
    """

    label: str
    url: str
