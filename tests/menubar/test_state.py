"""Menu bar preference persistence — ~/.quodeq/menubar_state.json."""
from __future__ import annotations

import json

from quodeq.menubar.state import (
    MenubarState,
    get_menubar_state_path,
    is_enabled,
    read_state,
    set_enabled,
    write_state,
)


def test_default_is_disabled(tmp_path):
    env = {"QUODEQ_DIR": str(tmp_path)}
    assert read_state(env) == MenubarState(enabled=False)
    assert is_enabled(env) is False


def test_set_enabled_roundtrip(tmp_path):
    env = {"QUODEQ_DIR": str(tmp_path)}
    set_enabled(True, env)
    assert is_enabled(env) is True
    assert json.loads((tmp_path / "menubar_state.json").read_text()) == {"enabled": True}
    set_enabled(False, env)
    assert is_enabled(env) is False


def test_corrupt_file_falls_back_to_defaults(tmp_path):
    env = {"QUODEQ_DIR": str(tmp_path)}
    (tmp_path / "menubar_state.json").write_text("{not json")
    assert read_state(env) == MenubarState()


def test_non_dict_json_falls_back_to_defaults(tmp_path):
    env = {"QUODEQ_DIR": str(tmp_path)}
    (tmp_path / "menubar_state.json").write_text('["enabled"]')
    assert read_state(env) == MenubarState()


def test_unknown_keys_ignored(tmp_path):
    env = {"QUODEQ_DIR": str(tmp_path)}
    (tmp_path / "menubar_state.json").write_text('{"enabled": true, "mystery": 1}')
    assert read_state(env) == MenubarState(enabled=True)


def test_explicit_path_env_wins(tmp_path):
    explicit = tmp_path / "elsewhere" / "custom.json"
    env = {"QUODEQ_DIR": str(tmp_path), "QUODEQ_MENUBAR_STATE_PATH": str(explicit)}
    assert get_menubar_state_path(env) == str(explicit)
    write_state(MenubarState(enabled=True), env)
    assert explicit.exists()
    assert is_enabled(env) is True
