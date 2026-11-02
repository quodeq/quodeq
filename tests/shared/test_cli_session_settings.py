import json
from pathlib import Path

from quodeq.shared.cli_session_settings import session_settings_args

_SPEC = {"flag": "--settings", "settings": {"permissions": {
    "allow": ["mcp(srv/*)", "read_file({repo})"], "deny": ["command(*)"]}}}


def test_repo_placeholder_is_filled_with_the_resolved_repo(tmp_path):
    flag, payload = session_settings_args(_SPEC, tmp_path)
    assert flag == "--settings"
    assert json.loads(payload)["permissions"]["allow"] == ["mcp(srv/*)", f"read_file({tmp_path.resolve()})"]


def test_a_repo_rule_without_a_repo_emits_nothing():
    assert session_settings_args(_SPEC) == []


def test_settings_without_placeholders_need_no_repo():
    spec = {"settings": {"toolPermission": "strict"}}
    assert session_settings_args(spec) == ["--settings", '{"toolPermission":"strict"}']


def test_no_spec_emits_nothing():
    assert session_settings_args(None, Path("/repo")) == []
    assert session_settings_args({"flag": "--settings"}, Path("/repo")) == []
