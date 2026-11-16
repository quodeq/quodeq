"""A CLI that is not installed reads the same on Windows as it did before.

``launch_argv`` refuses a bare name found in no PATH directory. Before, the
bare name went on to the spawn, which failed with the same
``FileNotFoundError``; each caller below must still end in its usual
"not installed" outcome, never in a crash or a half-built result.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.analysis.codex_sandbox import native_sandbox_works
from quodeq.assistant.mcp import mcp_config
from quodeq.data.cli_models import CatalogUnavailable, fetch_cli_model_catalog, run_cli_models_command
from quodeq.shared.win_launch import launch_argv


@pytest.fixture
def nothing_installed(tmp_path, monkeypatch) -> dict[str, str]:
    """Windows launch rules with a PATH that holds no program at all."""
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setattr("quodeq.shared.win_launch.IS_WIN32", True)
    monkeypatch.setenv("PATH", str(empty))
    return {"PATH": str(empty)}


def test_the_spawn_raises_what_a_missing_program_always_raised(nothing_installed):
    with pytest.raises(FileNotFoundError) as caught:
        launch_argv(["claude", "-p", "hi"], nothing_installed)
    assert caught.value.filename == "claude"


def test_assistant_mcp_registration_reports_it_could_not_register(nothing_installed):
    with pytest.raises(RuntimeError, match="Could not register"):
        mcp_config.register_cli_mcp("codex", [])


def test_assistant_mcp_unregistration_stays_silent(nothing_installed):
    mcp_config.unregister_cli_mcp("codex")


def test_model_listing_is_empty(nothing_installed):
    assert run_cli_models_command("claude", timeout_s=1) == ""


def test_model_catalog_is_unavailable(nothing_installed):
    with pytest.raises(CatalogUnavailable, match="not installed"):
        fetch_cli_model_catalog("claude", env=nothing_installed, timeout_s=1)


def test_codex_sandbox_probe_says_no(nothing_installed, tmp_path):
    sample = tmp_path / "sample.txt"
    sample.write_text("x", encoding="utf-8")
    assert native_sandbox_works("codex", ["--full-auto"], Path(tmp_path), sample, nothing_installed) is False
