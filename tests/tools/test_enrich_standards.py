"""Unit tests for tools/enrich_standards.py."""
from __future__ import annotations


def test_get_highest_id_skips_malformed_with_stderr_diagnostic(capsys):
    """Malformed requirement ids are skipped with a diagnostic to stderr."""
    import enrich_standards

    reqs = [
        {"id": "ABC-001"},
        {"id": "ABC-002"},
        {"id": "ABC-malformed"},  # not a valid int
        {"id": "ABC-003"},
    ]

    result = enrich_standards._get_highest_id(reqs, "ABC")

    # Should skip the malformed one and return the highest valid number (3)
    assert result == 3

    # Should have logged the malformed id to stderr
    captured = capsys.readouterr()
    assert "Skipping malformed requirement id:" in captured.err
    assert "ABC-malformed" in captured.err


def test_get_highest_id_returns_zero_when_no_matching_prefix():
    """When no requirements match the prefix, returns 0."""
    import enrich_standards

    reqs = [
        {"id": "XYZ-001"},
        {"id": "XYZ-002"},
    ]

    result = enrich_standards._get_highest_id(reqs, "ABC")

    assert result == 0


def test_get_highest_id_handles_only_valid_ids():
    """When all ids are valid, returns the highest number."""
    import enrich_standards

    reqs = [
        {"id": "ABC-001"},
        {"id": "ABC-005"},
        {"id": "ABC-003"},
    ]

    result = enrich_standards._get_highest_id(reqs, "ABC")

    assert result == 5
