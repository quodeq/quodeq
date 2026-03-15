from quodeq.config.coverage import coverage_percent, parse_coverage_percent


def test_coverage_percent_parses_fraction():
    assert coverage_percent("3/10") == 30


def test_coverage_percent_zero_denominator():
    assert coverage_percent("5/0") == 0


def test_coverage_percent_invalid_numerator():
    assert coverage_percent("abc/10") == 0


def test_coverage_percent_invalid_denominator():
    assert coverage_percent("5/abc") == 0


def test_coverage_percent_percentage_string():
    assert coverage_percent("85%") == 85


def test_coverage_percent_plain_number():
    assert coverage_percent("42") == 42


def test_coverage_percent_invalid_input():
    assert coverage_percent("not-a-number") == 0


def test_parse_coverage_percent_strips_whitespace():
    assert parse_coverage_percent("  75%  ") == 75


def test_parse_coverage_percent_invalid():
    assert parse_coverage_percent("abc") == 0
