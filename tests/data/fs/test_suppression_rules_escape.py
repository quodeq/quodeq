"""load_suppression_rules: a failure outside its narrow catches must propagate.

Split out from tests/services/test_suppression_rules.py to keep that file
under the size ratchet's 300-line cap. See that file's TestLoadSuppressionRules
for the degrade-on-malformed-input coverage; this sibling covers the other
half of the reliability-cycle-2 narrowing -- an unnamed exception is a real
bug, not advisory-data noise, and must reach the caller rather than being
silently absorbed as "no rules".
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.data.fs.suppression_rules import load_suppression_rules


def test_an_unnamed_read_failure_propagates(tmp_path, monkeypatch):
    """The catch narrows to (OSError, ValueError, RecursionError); a bug
    that raises anything else must not be silently absorbed as 'no rules'."""
    (tmp_path / "suppression_rules.json").write_text(json.dumps({
        "rules": [{"req": "X-1", "file": "a.py", "reason": "r"}],
    }), encoding="utf-8")

    def _boom(self, *a, **kw):
        raise RuntimeError("unexpected read failure")

    monkeypatch.setattr(Path, "read_text", _boom)
    with pytest.raises(RuntimeError, match="unexpected read failure"):
        load_suppression_rules(tmp_path)
