"""The prompt must brief the model on a declared trust model, and its
vocabulary must stay in sync with the deterministic gate."""
from __future__ import annotations

from quodeq.analysis.api_prompt_assembly import _format_shape_block
from quodeq.context.project_shape import Deployment, ProjectShape
from quodeq.context.trust_model import CONSERVATIVE, TrustModel

LOCAL = TrustModel(multi_tenant=False, network_exposure="loopback")
PUBLIC_SINGLE_TENANT = TrustModel(multi_tenant=False, network_exposure="public")
DESKTOP_SHAPE = ProjectShape(deployment=Deployment.DESKTOP, is_single_user=True)


def test_loopback_note_advises_minor_not_omission():
    # I3: the note must advise the same thing the gate enforces -- report at
    # minor, never omit -- not a blanket "does not apply".
    block = _format_shape_block(DESKTOP_SHAPE, LOCAL).lower()
    assert "path" in block
    assert "minor" in block
    assert "not apply" not in block
    assert "omit" in block


def test_conservative_model_adds_no_relaxing_note():
    block = _format_shape_block(DESKTOP_SHAPE, CONSERVATIVE).lower()
    assert "no untrusted" not in block


def test_block_renders_when_shape_unknown_but_model_declared():
    # The declaration is the authority. An UNKNOWN shape must no longer
    # suppress the briefing when the team has told us the answer.
    block = _format_shape_block(ProjectShape(), LOCAL)
    assert block, "a declared trust model must be briefed even without a shape verdict"
    assert "loopback" in block


def test_still_empty_when_nothing_is_known():
    assert _format_shape_block(ProjectShape(), CONSERVATIVE) == ""


# --- I3 / minor #4: the single-tenant half was untested --------------------

def test_single_tenant_note_advises_minor_not_does_not_apply():
    block = _format_shape_block(DESKTOP_SHAPE, LOCAL).lower()
    assert "not apply" not in block
    assert "one user" in block
    assert "minor" in block


def test_single_tenant_note_omitted_without_loopback():
    # The gate's cross-principal rule requires BOTH axes (multi_tenant=False
    # AND relaxes_remote()) -- see test_cross_principal_untouched_when_public
    # _single_tenant in test_scope_gate.py. A public single-tenant model must
    # not get authorization-relaxing advice the gate would never honor for
    # it: a public-facing single-user service missing an authz check is
    # still genuinely vulnerable to an unauthenticated stranger.
    block = _format_shape_block(DESKTOP_SHAPE, PUBLIC_SINGLE_TENANT).lower()
    assert "one user" not in block
    assert "authorization" not in block


def test_no_note_claims_a_category_does_not_apply():
    for model in (LOCAL, PUBLIC_SINGLE_TENANT, CONSERVATIVE):
        block = _format_shape_block(DESKTOP_SHAPE, model).lower()
        assert "not apply" not in block
