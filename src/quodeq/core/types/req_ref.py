"""The requirement back-reference carried by findings and judgments."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from quodeq.core.standards.refs import label_from_url, ref_label


@dataclass(frozen=True, slots=True)
class ReqRef:
    """A link from a finding back to the requirement it was judged against.

    Built by ``core.finding_mappings._coerce_req_refs`` from whatever the
    model emitted, so both fields can be empty strings.
    """

    label: str
    url: str

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> ReqRef:
        """A ReqRef from a stored ref dict, labelled or in the standard's shape.

        Since admission (2026-09-29) the evidence stores the standard's own ref
        (``source``/``id``/``name``/``url``) with no ``label``; the label is
        derived from ``source`` and ``id`` so the card still names the link.
        Reports built from that evidence kept only the url, so it is the
        last resort.
        """
        url = str(raw.get("url") or "")
        label = raw.get("label") or ""
        if not label and (raw.get("source") or raw.get("id")):
            label = ref_label(dict(raw))
        return cls(label=str(label or label_from_url(url)), url=url)
