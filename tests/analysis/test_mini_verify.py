from unittest.mock import patch, MagicMock

from quodeq.analysis.subagents._verification import _dispatch_mini_verify


@patch("quodeq.analysis.subagents._verification._run_verification_pool")
def test_mini_verify_caps_agents(mock_pool, tmp_path):
    mock_pool.return_value = []
    config = MagicMock()
    config.src = tmp_path
    config.standards_dir = None
    config.options.max_subagents = 10
    config.options.ai_model = None
    config.options.pool_budget = 300

    findings = [
        {"file": f"f{i}.py", "p": "S", "t": "violation", "line": 1, "reason": "r"}
        for i in range(50)
    ]
    _dispatch_mini_verify(config, "security", tmp_path, findings)
    assert mock_pool.called


@patch("quodeq.analysis.subagents._verification._run_verification_pool")
def test_mini_verify_skips_empty(mock_pool, tmp_path):
    config = MagicMock()
    result = _dispatch_mini_verify(config, "security", tmp_path, [])
    assert result == []
    assert not mock_pool.called
