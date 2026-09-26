"""resolve_trust_model: a failure outside its narrow catches must propagate.

Sibling of test_trust_model.py, which covers the degrade-on-malformed-input
tests; this file covers the other half of the reliability-cycle-2 narrowing --
an unnamed exception is a real bug, not advisory-data noise, and must reach
the per-dim/startup fault-isolation boundary rather than be silently absorbed.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.context import trust_model as trust_model_module
from quodeq.context.trust_model import resolve_trust_model

from ._trust_model_helpers import _write_profile


def test_an_unnamed_profile_read_failure_propagates(tmp_path, monkeypatch):
    """_read_profile's except narrows to (OSError, ValueError,
    RecursionError); anything else reading the declared profile must
    propagate, not be swallowed."""
    _write_profile(tmp_path, {"version": 1})

    def _boom(self, *a, **kw):
        raise RuntimeError("unexpected read failure")

    monkeypatch.setattr(Path, "read_text", _boom)
    with pytest.raises(RuntimeError, match="unexpected read failure"):
        resolve_trust_model(tmp_path)


def test_an_unnamed_detection_failure_propagates(tmp_path, monkeypatch):
    """_detected_multi_tenant no longer wraps detect_shape in its own
    try/except: a genuine bug in shape detection must propagate, not be
    silently absorbed as 'unknown'."""
    def _boom(_root):
        raise RuntimeError("unexpected detection failure")

    monkeypatch.setattr(trust_model_module, "detect_shape", _boom)
    with pytest.raises(RuntimeError, match="unexpected detection failure"):
        resolve_trust_model(tmp_path)
