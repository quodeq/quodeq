"""Cluster 37: update best-effort handlers log at debug."""
from __future__ import annotations

from unittest.mock import patch

from quodeq.shared import json_state
from quodeq.update import state


def test_write_state_logs_write_and_cleanup_failures(monkeypatch, tmp_path) -> None:
    env = {"QUODEQ_DIR": str(tmp_path)}
    current = state.read_state(env)  # read_state(env) -> UpdateState; write_state(state, env)

    def _replace_fails(*_args, **_kwargs):
        raise OSError(28, "No space left on device")

    def _unlink_fails(*_args, **_kwargs):
        raise OSError(13, "Permission denied")

    monkeypatch.setattr(json_state.os, "replace", _replace_fails)
    monkeypatch.setattr(json_state.os, "unlink", _unlink_fails)
    with patch.object(state._logger, "debug") as debug:
        state.write_state(current, env)
    messages = [c.args[0] for c in debug.call_args_list]
    assert any("state write failed" in m for m in messages)
    assert any("not removed" in m for m in messages)
