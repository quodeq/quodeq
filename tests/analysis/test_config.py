"""Defensive env parsing for the single-agent turn/duration ceilings.

QUODEQ_DEFAULT_MAX_TURNS/DURATION used to be read by AnalysisConfig's field
defaults on every construction. The CLI now resolves them once per run into
AnalysisOptions, and AnalysisConfig itself reads nothing from the env.
"""
import argparse


def _run_options(tmp_path):
    from quodeq.cli import ResolvedInputs, build_run_config

    args = argparse.Namespace(
        dimensions=None, no_consolidated=False, no_verify=False, max_turns=None,
        max_duration=None, n_subagents=1, pool_budget=None, clean_scan=False,
        legacy_incremental=False,
    )
    inputs = ResolvedInputs(src=tmp_path, language="python", manifest=None, dims_data={})
    return build_run_config(args, inputs=inputs, evidence_dir=tmp_path).options


def test_invalid_max_turns_env_falls_back_to_default(monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_DEFAULT_MAX_TURNS", "not-a-number")
    assert _run_options(tmp_path).default_max_turns == 200


def test_invalid_max_duration_env_falls_back_to_default(monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_DEFAULT_MAX_DURATION", "")
    assert _run_options(tmp_path).default_max_duration == 1800


def test_valid_values_are_read_once_per_run(monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_DEFAULT_MAX_TURNS", "42")
    monkeypatch.setenv("QUODEQ_DEFAULT_MAX_DURATION", "77")
    options = _run_options(tmp_path)
    assert (options.default_max_turns, options.default_max_duration) == (42, 77)


def test_analysis_config_no_longer_reads_the_env(monkeypatch):
    from quodeq.analysis.subprocess import AnalysisConfig

    monkeypatch.setenv("QUODEQ_DEFAULT_MAX_TURNS", "42")
    monkeypatch.setenv("QUODEQ_DEFAULT_MAX_DURATION", "77")
    cfg = AnalysisConfig()
    assert (cfg.max_turns, cfg.max_duration) == (None, None)


def test_injected_env_is_honoured():
    from quodeq.config.analysis_env import default_max_duration, default_max_turns

    assert default_max_turns({"QUODEQ_DEFAULT_MAX_TURNS": "11"}) == 11
    assert default_max_duration({"QUODEQ_DEFAULT_MAX_DURATION": "22"}) == 22
