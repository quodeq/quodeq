"""Defensive env parsing for the analysis config defaults.

These used to be import-time constants, so this test had to reload the
module with the env var set and reload again to restore it. The defaults
now resolve per construction, so the seam is exercised directly.
"""


def test_invalid_max_turns_env_falls_back_to_default(monkeypatch):
    from quodeq.analysis._config import AnalysisConfig

    monkeypatch.setenv("QUODEQ_DEFAULT_MAX_TURNS", "not-a-number")
    assert AnalysisConfig().max_turns == 200


def test_invalid_max_duration_env_falls_back_to_default(monkeypatch):
    from quodeq.analysis._config import AnalysisConfig

    monkeypatch.setenv("QUODEQ_DEFAULT_MAX_DURATION", "")
    assert AnalysisConfig().max_duration == 1800


def test_injected_env_is_honoured():
    from quodeq.config.analysis_env import default_max_duration, default_max_turns

    assert default_max_turns({"QUODEQ_DEFAULT_MAX_TURNS": "11"}) == 11
    assert default_max_duration({"QUODEQ_DEFAULT_MAX_DURATION": "22"}) == 22
