"""Guards on AI_CMD-derived subprocess execution in analysis._command."""
import logging
import subprocess

from quodeq.analysis._command import _register_cli_mcp, _unregister_cli_mcp
from quodeq.analysis._config import AnalysisConfig


def test_register_cli_mcp_rejects_unknown_provider(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "quodeq.analysis._command.subprocess.run",
        lambda *a, **k: calls.append(a),
    )
    result = _register_cli_mcp("rm -rf /", AnalysisConfig())
    assert result is None
    assert calls == []


def test_unregister_cli_mcp_rejects_unknown_provider(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "quodeq.analysis._command.subprocess.run",
        lambda *a, **k: calls.append(a),
    )
    _unregister_cli_mcp("rm -rf /", "some-server-name")
    assert calls == []


def test_unregister_cli_mcp_logs_on_subprocess_failure(monkeypatch, caplog):
    """A failing `<cmd> mcp remove` must be logged, not silently swallowed."""
    monkeypatch.setattr(
        "quodeq.analysis._command.subprocess.run",
        lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired(cmd="claude", timeout=5)),
    )
    with caplog.at_level(logging.WARNING):
        _unregister_cli_mcp("claude", "quodeq-findings")

    assert any(
        "unregister" in r.message.lower() and "quodeq-findings" in r.message
        for r in caplog.records
    ), f"expected a warning naming the server, got: {[r.message for r in caplog.records]}"


def test_register_cli_mcp_allows_known_cli_provider(monkeypatch, tmp_path):
    """A registered type='cli' provider (claude) still reaches subprocess.run."""
    calls = []
    monkeypatch.setattr(
        "quodeq.analysis._command.subprocess.run",
        lambda *a, **k: calls.append(a),
    )
    # Reset the module-level registration cache so this call is not short-circuited.
    monkeypatch.setattr("quodeq.analysis._command._cli_mcp_registered", set())
    config = AnalysisConfig(jsonl_file=tmp_path / "findings.jsonl")
    result = _register_cli_mcp("claude", config)
    assert result is not None
    assert calls  # subprocess.run was invoked (register, and possibly unregister)
