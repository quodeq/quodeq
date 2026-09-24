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

    {"version": 1, "multiTenant": false, "networkExposure": "loopback",
     "deploymentTopology": "single-host"}

Resolution is PER FIELD: a declared value wins, ``detect_shape`` fills what is
undeclared, and anything still unknown falls back to :data:`CONSERVATIVE`. That
last step is the no-regression guarantee -- a project that declares nothing and
detects as nothing is scored exactly as it was before this module existed.

That per-field fallback is deliberately ASYMMETRIC between the axes.
``multi_tenant`` is a property a manifest can genuinely evidence -- a CLI's
own entry point is real proof it has one caller. Network exposure is not: a
loopback Flask app and a hosted one are byte-identical on disk, the same
point made two paragraphs up. So ``_detected_multi_tenant`` is the only
detection step, and it fills ``multi_tenant`` alone -- detection is never
allowed to waive a remote-reachability finding by itself. A Rust
``axum`` service with only a ``main.rs``, a Django app that merely lists
``pyinstaller`` in a dev extra, or an Express service with ``electron`` in
``devDependencies`` all detect as desktop/CLI today; none of them may get
``S-AUT-3``/``S-AUT-10`` waived on that basis alone. Only a human's
declaration in ``project-profile.json`` may relax that axis.
``deployment_topology`` is declaration-only for exactly the same reason: a
single-host deployment and a horizontally scaled one are byte-identical on
disk, so detection never fills it either.

Nothing here may fail a scan. Every malformed-input branch warns and degrades.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from quodeq.context.project_shape import Deployment, detect_shape

_logger = logging.getLogger(__name__)

PROFILE_RELPATH = Path(".quodeq") / "project-profile.json"

SUPPORTED_VERSION = 1


class NetworkExposure(StrEnum):
    """project-profile.json's declared "networkExposure" values.

    Only ``LOOPBACK`` relaxes anything. ``LAN`` is accepted so a team can
    describe itself honestly rather than mis-declaring as loopback, and so a
    later rule can use it without a file-format migration, but it grants
    nothing today: a LAN is not a trust boundary this code can reason about.
    """

    LOOPBACK = "loopback"
    LAN = "lan"
    PUBLIC = "public"


NETWORK_EXPOSURES: frozenset[str] = frozenset(
    {NetworkExposure.LOOPBACK, NetworkExposure.LAN, NetworkExposure.PUBLIC},
)

_TOPOLOGY_SINGLE_HOST = "single-host"

#: Topology is never detected, for the same reason exposure is not: a
#: single-host deployment and a horizontally scaled one are byte-identical on
#: disk. Only a human declaration may relax F-SCL-1/2/4.
DEPLOYMENT_TOPOLOGIES: frozenset[str] = frozenset({_TOPOLOGY_SINGLE_HOST, "distributed"})


@dataclass(frozen=True)
class TrustModel:
    """The axes a finding's severity can legitimately turn on."""

    multi_tenant: bool
    network_exposure: str
    deployment_topology: str

    def relaxes_remote(self) -> bool:
        """True when no untrusted party can open a socket to this process."""
        return self.network_exposure == NetworkExposure.LOOPBACK

    def is_single_host(self) -> bool:
        """True when the team declared this runs as one process on one host."""
        return self.deployment_topology == _TOPOLOGY_SINGLE_HOST


#: What an undeclared, undetectable project gets. Deliberately the most
#: pessimistic model, so absence of information never relaxes a finding.
CONSERVATIVE = TrustModel(
    multi_tenant=True, network_exposure="public", deployment_topology="distributed")


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


def _enum_field(data: dict, key: str, allowed: frozenset[str] | set[str]) -> str | None:
    """The declared *key*, normalised, when it names one of *allowed*.

    None for an absent field and for a bad one, which is warned about: the
    file is a declaration, not a transaction, so one bad axis never discards
    the others.
    """
    raw = data.get(key)
    if isinstance(raw, str) and raw.strip().lower() in allowed:
        return raw.strip().lower()
    if raw is not None:
        _logger.warning(
            "project profile: %s must be one of %s, got %r", key, sorted(allowed), raw,
        )
    return None


def _declared_fields(data: dict) -> tuple[bool | None, str | None, str | None]:
    """Extract the three axes from a parsed profile, per field.

    A bad value for one axis never discards the other: the file is a
    declaration, not a transaction.
    """
    multi_tenant: bool | None = None
    raw_tenant = data.get("multiTenant")
    if isinstance(raw_tenant, bool):
        multi_tenant = raw_tenant
    elif raw_tenant is not None:
        _logger.warning("project profile: multiTenant must be a boolean, got %r", raw_tenant)

    exposure = _enum_field(data, "networkExposure", NETWORK_EXPOSURES)
    topology = _enum_field(data, "deploymentTopology", DEPLOYMENT_TOPOLOGIES)
    return multi_tenant, exposure, topology


def _detected_multi_tenant(project_root: Path) -> bool | None:
    """Derive ``multi_tenant`` from manifest detection; None when unknown.

    This is the only trust axis detection may fill -- see the module
    docstring for why exposure and topology are declaration-only. A CLI's
    own entry point is real evidence of a single caller. ``LIBRARY`` still
    maps to unknown on purpose: ``_shape_irrelevant_to_hosted_service``
    treats libraries as non-hosted, which is sound for concurrency findings
    and wrong here, because a library's paths may be fed from an HTTP
    request in the consuming application and the author cannot know.
    """
    try:
        shape = detect_shape(project_root)
    except Exception as exc:  # noqa: BLE001 - unreadable/pathological manifests must not fail a scan
        # detect_shape's own manifest readers (project_shape.py) only catch
        # OSError/tomllib.TOMLDecodeError/json.JSONDecodeError, not every
        # failure mode: deeply nested package.json/pyproject.toml/Cargo.toml
        # content overflows the C JSON decoder's or tomllib's recursion limit
        # and raises RecursionError, a RuntimeError subclass neither of those
        # readers catches. project_root is analyzed, untrusted input with a
        # well-defined conservative fallback, so any detection failure -- not
        # just OSError -- must degrade here rather than escape and fail the
        # scan. project_shape.py itself is out of scope for this fix; this
        # catch is deliberately wide as the boundary that must not leak.
        _logger.warning("Project shape detection failed for %s: %s", project_root, exc)
        return None
    if shape.deployment is Deployment.WEB_SERVICE:
        return True
    if shape.deployment is Deployment.DESKTOP:
        return False
    if shape.deployment is Deployment.CLI and shape.is_single_user:
        return False
    return None


def resolve_trust_model(project_root: Path | str | None) -> TrustModel:
    """Resolve the effective trust model for *project_root*.

    Per field: declared, then detected, then :data:`CONSERVATIVE`.
    """
    if not project_root:
        return CONSERVATIVE
    root = Path(project_root)
    declared_tenant, declared_exposure, declared_topology = _declared_fields(_read_profile(root))
    multi_tenant = declared_tenant
    if multi_tenant is None:
        multi_tenant = _detected_multi_tenant(root)
    if multi_tenant is None:
        multi_tenant = CONSERVATIVE.multi_tenant

    exposure = declared_exposure or CONSERVATIVE.network_exposure
    topology = declared_topology or CONSERVATIVE.deployment_topology
    return TrustModel(
        multi_tenant=multi_tenant,
        network_exposure=exposure,
        deployment_topology=topology,
    )
