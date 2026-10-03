"""Rules the enrichment steps in ``enricher.py`` share.

The confidence downweights and the principle fallback live here rather than
in ``enricher.py``, which sits near the size ratchet's 300-line cap.
"""
from __future__ import annotations

from quodeq.context.path_role import NON_PROD_ROLES, path_role
from quodeq.context.project_shape import Deployment, ProjectShape
from quodeq.core.constants import FULL_CONFIDENCE
from quodeq.core.types.finding_type import FindingType

# These downweights set `confidence`, a UI/triage signal only; it does not
# affect the grade (see enricher.py).
_NON_PROD_DOWNWEIGHT = 50
_SHAPE_DOWNWEIGHT = 40

_HOSTED_SERVICE_KEYWORDS: tuple[str, ...] = (
    "concurrent caller", "concurrent callers", "concurrent request",
    "concurrent requests", "thread block", "blocks the thread",
    "blocks thread", "blocks the event loop", "blocks the request thread",
    "distributed state", "distributed system", "distributed lock",
    "multi-tenant", "multitenant", "tenant isolation",
    "rate limit", "rate-limit", "rate limiting",
    "ddos", "denial of service", "denial-of-service",
    "horizontal scaling", "horizontal scale",
)


def apply_downweight(finding: dict[str, object], value: int) -> None:
    """Set *value* as the finding's confidence, unless the model already lowered it.

    A confidence the model emitted below 100 is its own judgement and is left
    alone; an unset or full confidence is what a heuristic downweight is for.
    """
    existing = finding.get("confidence")
    if existing is None or existing == FULL_CONFIDENCE:
        finding["confidence"] = value


def resolve_principle(declared: object, req: object, reqs: dict) -> object:
    """The principle the model declared, or the requirement's when it declared none.

    One rule for both readers of it: the dedup key and the finding's own
    ``p`` field, which would otherwise be free to disagree.
    """
    if not declared and req and req in reqs:
        return reqs[req]["principle"]
    return declared


def apply_path_role_downweight(finding: dict[str, object]) -> None:
    """Lower confidence to 50 when the finding lives on a non-prod path.

    Skipped when the LLM emitted an explicit confidence below 100 and for
    compliance findings (downweighting "code is fine" makes no sense).
    """
    if finding.get("t") != FindingType.VIOLATION:
        return
    role = path_role(finding.get("file"))
    if role not in NON_PROD_ROLES:
        return
    apply_downweight(finding, _NON_PROD_DOWNWEIGHT)


def _shape_irrelevant_to_hosted_service(shape: ProjectShape | None) -> bool:
    """True when the project clearly isn't a hosted multi-tenant service."""
    if shape is None:
        return False
    if shape.deployment in (Deployment.DESKTOP, Deployment.LIBRARY):
        return True
    if shape.deployment is Deployment.CLI and shape.is_single_user:
        return True
    return False


def apply_shape_downweight(
    finding: dict[str, object], shape: ProjectShape | None,
) -> None:
    """Downweight findings that assume a hosted service when the project isn't one."""
    if finding.get("t") != FindingType.VIOLATION:
        return
    if not _shape_irrelevant_to_hosted_service(shape):
        return
    haystack_parts: list[str] = []
    for key in ("reason", "w", "title"):
        val = finding.get(key)
        if isinstance(val, str):
            haystack_parts.append(val.lower())
    haystack = " ".join(haystack_parts)
    if not any(kw in haystack for kw in _HOSTED_SERVICE_KEYWORDS):
        return
    apply_downweight(finding, _SHAPE_DOWNWEIGHT)
