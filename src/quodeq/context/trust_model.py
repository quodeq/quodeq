"""Per-project declared threat model.

Quodeq scores every project as if it were a hosted multi-tenant service. For a
local-first tool that is wrong in a measurable way: a path built from a value
the operator already controls is reported as an attack surface. See
``project_shape``'s own docstring -- shape assumptions are the largest single
FP source in the audit corpus.

Detection cannot fix this on its own. The manifest of a loopback Flask app is
byte-identical to that of a hosted one; whether an untrusted party can open a
socket is information only the team has. So the model is DECLARED, in the
analyzed repository at ``<project root>/.quodeq/project-profile.json``,
alongside ``standards-visibility.json`` and ``standards-overrides.json`` so the
whole team shares it:

    {"version": 1, "multiTenant": false, "networkExposure": "loopback"}

Resolution is PER FIELD: a declared value wins, ``detect_shape`` fills what is
undeclared, and anything still unknown falls back to :data:`CONSERVATIVE`. That
last step is the no-regression guarantee -- a project that declares nothing and
detects as nothing is scored exactly as it was before this module existed.

Nothing here may fail a scan. Every malformed-input branch warns and degrades.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from quodeq.context.project_shape import Deployment, detect_shape

_logger = logging.getLogger(__name__)

PROFILE_RELPATH = Path(".quodeq") / "project-profile.json"

SUPPORTED_VERSION = 1

# Only ``loopback`` relaxes anything. ``lan`` is accepted so a team can describe
# itself honestly rather than mis-declaring as loopback, and so a later rule can
# use it without a file-format migration, but it grants nothing today: a LAN is
# not a trust boundary this code can reason about.
NETWORK_EXPOSURES: frozenset[str] = frozenset({"loopback", "lan", "public"})


@dataclass(frozen=True)
class TrustModel:
    """The two axes a finding's severity can legitimately turn on."""

    multi_tenant: bool
    network_exposure: str

    def relaxes_remote(self) -> bool:
        """True when no untrusted party can open a socket to this process."""
        return self.network_exposure == "loopback"


#: What an undeclared, undetectable project gets. Deliberately the most
#: pessimistic model, so absence of information never relaxes a finding.
CONSERVATIVE = TrustModel(multi_tenant=True, network_exposure="public")


def _read_profile(project_root: Path) -> dict:
    """Parse the profile file; ``{}`` for absent, unreadable or malformed.

    This is advisory data an operator hand-writes, with a well-defined
    conservative fallback, so parsing failures of *any* kind degrade rather
    than propagate -- not just the well-behaved ``OSError``/``ValueError``/
    ``UnicodeDecodeError`` trio. In particular, deeply nested JSON (e.g. tens
    of thousands of nested arrays) overflows the C decoder's call stack and
    raises ``RecursionError``, which is a ``RuntimeError`` and would
    otherwise escape and fail the scan.
    """
    path = project_root / PROFILE_RELPATH
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - advisory data must never fail a scan
        _logger.warning("Ignoring unreadable or malformed project profile %s: %s", path, exc)
        return {}
    if not isinstance(data, dict):
        _logger.warning("Ignoring project profile %s: not a JSON object", path)
        return {}
    version = data.get("version")
    # ``bool`` is a subclass of ``int`` in Python, so ``True == 1``: without the
    # explicit bool exclusion, a profile declaring ``"version": true`` would
    # silently pass this gate as version 1.
    if isinstance(version, bool) or not isinstance(version, int) or version != SUPPORTED_VERSION:
        _logger.warning(
            "Ignoring project profile %s: unsupported version %r (expected %d)",
            path, version, SUPPORTED_VERSION,
        )
        return {}
    return data


def _declared_fields(data: dict) -> tuple[bool | None, str | None]:
    """Extract the two axes from a parsed profile, per field.

    A bad value for one axis never discards the other: the file is a
    declaration, not a transaction.
    """
    multi_tenant: bool | None = None
    raw_tenant = data.get("multiTenant")
    if isinstance(raw_tenant, bool):
        multi_tenant = raw_tenant
    elif raw_tenant is not None:
        _logger.warning("project profile: multiTenant must be a boolean, got %r", raw_tenant)

    exposure: str | None = None
    raw_exposure = data.get("networkExposure")
    if isinstance(raw_exposure, str) and raw_exposure.strip().lower() in NETWORK_EXPOSURES:
        exposure = raw_exposure.strip().lower()
    elif raw_exposure is not None:
        _logger.warning(
            "project profile: networkExposure must be one of %s, got %r",
            sorted(NETWORK_EXPOSURES), raw_exposure,
        )
    return multi_tenant, exposure


def _detected_fields(project_root: Path) -> tuple[bool | None, str | None]:
    """Derive the two axes from manifest detection; ``None`` where unknown.

    ``LIBRARY`` maps to unknown on purpose. ``_shape_irrelevant_to_hosted_service``
    treats libraries as non-hosted, which is sound for concurrency findings and
    wrong for trust boundaries: a library's paths may be fed from an HTTP
    request in the consuming application, and the author cannot know.
    """
    try:
        shape = detect_shape(project_root)
    except OSError as exc:  # unreadable manifests must not fail a scan
        _logger.warning("Project shape detection failed for %s: %s", project_root, exc)
        return None, None
    if shape.deployment is Deployment.WEB_SERVICE:
        return True, "public"
    if shape.deployment is Deployment.DESKTOP:
        return False, "loopback"
    if shape.deployment is Deployment.CLI and shape.is_single_user:
        return False, "loopback"
    return None, None


def resolve_trust_model(project_root: Path | str | None) -> TrustModel:
    """Resolve the effective trust model for *project_root*.

    Per field: declared, then detected, then :data:`CONSERVATIVE`.
    """
    if not project_root:
        return CONSERVATIVE
    root = Path(project_root)
    declared_tenant, declared_exposure = _declared_fields(_read_profile(root))
    detected_tenant, detected_exposure = _detected_fields(root)

    multi_tenant = declared_tenant
    if multi_tenant is None:
        multi_tenant = detected_tenant
    if multi_tenant is None:
        multi_tenant = CONSERVATIVE.multi_tenant

    exposure = declared_exposure or detected_exposure or CONSERVATIVE.network_exposure
    return TrustModel(multi_tenant=multi_tenant, network_exposure=exposure)
