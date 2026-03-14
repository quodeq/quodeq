import pytest
from quodeq.config.coverage import parse_coverage_percent


def test_parse_coverage_percent():
    assert parse_coverage_percent("75%") == 75


def test_parse_coverage_percent_boundary_zero():
    assert parse_coverage_percent("0%") == 0


def test_parse_coverage_percent_boundary_100():
    assert parse_coverage_percent("100%") == 100


def test_parse_coverage_percent_no_suffix():
    assert parse_coverage_percent("42") == 42
