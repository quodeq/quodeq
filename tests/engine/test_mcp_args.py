"""Tests for MCP server argument parsing."""
from quodeq.analysis.mcp.args import parse_args

# When --dimension is set, parse_args (Task 3.5) requires --cache-root and
# --model-id too. These tests focus on the `dimensions` split logic, so we
# pass placeholder cache args to satisfy the enforcement.
_CACHE_ARGS = ["--cache-root", "/tmp/cache", "--model-id", "sonnet"]


class TestParseArgsDimensions:
    def test_single_dimension(self):
        args = parse_args(["output.jsonl", "--dimension", "security", *_CACHE_ARGS])
        assert args.dimensions == ["security"]
        assert args.dimension == "security"

    def test_comma_separated_dimensions(self):
        args = parse_args(["output.jsonl", "--dimension", "security,maintainability,reliability", *_CACHE_ARGS])
        assert args.dimensions == ["security", "maintainability", "reliability"]

    def test_no_dimension(self):
        args = parse_args(["output.jsonl"])
        assert args.dimensions == []

    def test_comma_separated_with_spaces(self):
        args = parse_args(["output.jsonl", "--dimension", "security, maintainability", *_CACHE_ARGS])
        assert args.dimensions == ["security", "maintainability"]
