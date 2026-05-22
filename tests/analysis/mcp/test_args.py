"""Tests for the MCP findings server CLI argument parser."""
from __future__ import annotations

from quodeq.analysis.mcp.args import ServerArgs, parse_args


def test_parse_args_accepts_cache_root_and_model_id(tmp_path):
    """--cache-root and --model-id are optional flat CLI args parsed into ServerArgs."""
    cache_root = tmp_path / "cache"
    args = parse_args([
        str(tmp_path / "findings.jsonl"),
        "--cache-root", str(cache_root),
        "--model-id", "sonnet",
    ])
    assert args.cache_root == str(cache_root)
    assert args.model_id == "sonnet"


def test_parse_args_cache_root_and_model_id_default_to_none():
    """When omitted, both fields default to None on ServerArgs.

    The hard-fail check on missing values lives in _build_router (Task 5)
    and CLI-level enforcement (Task 7), NOT here.
    """
    args = parse_args(["/tmp/findings.jsonl"])
    assert args.cache_root is None
    assert args.model_id is None


def test_server_args_defaults_for_new_fields():
    """ServerArgs() with no overrides exposes both new fields defaulted to None."""
    sa = ServerArgs()
    assert sa.cache_root is None
    assert sa.model_id is None


def test_parse_args_accepts_language(tmp_path):
    """--language is an optional CLI arg parsed into ServerArgs.language."""
    args = parse_args([
        str(tmp_path / "findings.jsonl"),
        "--language", "kotlin",
    ])
    assert args.language == "kotlin"


def test_parse_args_language_defaults_to_none():
    """When --language is omitted, ServerArgs.language is None."""
    args = parse_args(["/tmp/findings.jsonl"])
    assert args.language is None


def test_server_args_default_language_is_none():
    """ServerArgs() with no overrides exposes language defaulted to None."""
    sa = ServerArgs()
    assert sa.language is None
