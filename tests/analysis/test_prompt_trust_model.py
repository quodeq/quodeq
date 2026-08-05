"""The prompt must brief the model on a declared trust model, and its
vocabulary must stay in sync with the deterministic gate."""
from __future__ import annotations

from pathlib import Path

from quodeq.analysis.api_prompt_assembly import _format_shape_block
from quodeq.context.project_shape import Deployment, ProjectShape
from quodeq.context.trust_model import CONSERVATIVE, TrustModel

LOCAL = TrustModel(multi_tenant=False, network_exposure="loopback")
DESKTOP_SHAPE = ProjectShape(deployment=Deployment.DESKTOP, is_single_user=True)


def test_loopback_note_mentions_trust_boundaries():
    block = _format_shape_block(DESKTOP_SHAPE, LOCAL).lower()
    assert "path" in block
    assert "trust boundary" in block or "trust-boundary" in block


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
