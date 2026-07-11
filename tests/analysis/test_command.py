"""Guards on AI_CMD-derived subprocess execution in analysis._command."""
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
