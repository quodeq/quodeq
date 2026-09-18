"""Trust models and the finding builder shared by the test_scope_gate* siblings."""
from __future__ import annotations

from quodeq.context.trust_model import TrustModel

LOCAL = TrustModel(multi_tenant=False, network_exposure="loopback",
                   deployment_topology="distributed")
LAN = TrustModel(multi_tenant=False, network_exposure="lan",
                 deployment_topology="distributed")
PUBLIC = TrustModel(multi_tenant=False, network_exposure="public",
                    deployment_topology="distributed")
SINGLE_HOST = TrustModel(multi_tenant=False, network_exposure="loopback",
                         deployment_topology="single-host")


def _finding(**kw) -> dict:
    base = {"t": "violation", "req": "S-AUT-3", "severity": "major",
            "w": "Path traversal via job_id",
            "reason": "The job_id is used to construct a file path without validation."}
    base.update(kw)
    return base
