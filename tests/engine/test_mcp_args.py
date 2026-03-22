"""Tests for MCP server argument parsing."""
from quodeq.analysis.mcp.args import parse_args


class TestParseArgsDimensions:
    def test_single_dimension(self):
        args = parse_args(["output.jsonl", "--dimension", "security"])
        assert args.dimensions == ["security"]
        assert args.dimension == "security"

    def test_comma_separated_dimensions(self):
        args = parse_args(["output.jsonl", "--dimension", "security,maintainability,reliability"])
        assert args.dimensions == ["security", "maintainability", "reliability"]

    def test_no_dimension(self):
        args = parse_args(["output.jsonl"])
        assert args.dimensions == []

    def test_comma_separated_with_spaces(self):
        args = parse_args(["output.jsonl", "--dimension", "security, maintainability"])
        assert args.dimensions == ["security", "maintainability"]
