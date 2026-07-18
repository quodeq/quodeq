"""Tests for the MCP findings server CLI argument parser."""
from __future__ import annotations

import pytest

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


def test_parse_args_accepts_standards_dir(tmp_path):
    """--standards-dir is an optional CLI arg parsed into ServerArgs.standards_dir.

    Distinct from --compiled-dir: this is the standards ROOT (parent of
    compiled/), needed so build_cache_writer's params fingerprint looks in
    the right place instead of double-appending "compiled".
    """
    standards_dir = tmp_path / "standards"
    args = parse_args([
        str(tmp_path / "findings.jsonl"),
        "--standards-dir", str(standards_dir),
    ])
    assert args.standards_dir == str(standards_dir)


def test_parse_args_standards_dir_defaults_to_none():
    """When --standards-dir is omitted, ServerArgs.standards_dir is None."""
    args = parse_args(["/tmp/findings.jsonl"])
    assert args.standards_dir is None


def test_server_args_default_standards_dir_is_none():
    """ServerArgs() with no overrides exposes standards_dir defaulted to None."""
    sa = ServerArgs()
    assert sa.standards_dir is None


def test_parse_args_raises_when_dimension_set_without_cache_args():
    """parse_args enforces: --dimension requires --cache-root and --model-id.

    Without both, the subprocess fails fast at parse time (defense-in-depth
    alongside _build_router's runtime check).
    """
    # Each subcase should fail because at least one of cache-root/model-id is missing.
    missing_cases = [
        # No cache args at all
        ["/tmp/findings.jsonl", "--dimension", "flexibility"],
        # cache-root only
        ["/tmp/findings.jsonl", "--dimension", "flexibility", "--cache-root", "/tmp/cache"],
        # model-id only
        ["/tmp/findings.jsonl", "--dimension", "flexibility", "--model-id", "sonnet"],
    ]
    for args in missing_cases:
        with pytest.raises((SystemExit, ValueError)):
            parse_args(args)


def test_parse_args_succeeds_when_dimension_set_with_all_required_cache_args():
    """When --dimension is set AND --cache-root + --model-id are provided,
    parse_args returns ServerArgs successfully. --language is optional at
    parse time (defaults to None), required only for cross-path key equality.
    """
    args = parse_args([
        "/tmp/findings.jsonl",
        "--dimension", "flexibility",
        "--cache-root", "/tmp/cache",
        "--model-id", "sonnet",
        # --language omitted: should still succeed (defaults to None)
    ])
    assert args.dimension == "flexibility"
    assert args.cache_root == "/tmp/cache"
    assert args.model_id == "sonnet"
    assert args.language is None
