from quodeq.core.scoring import report_grades as rg
from quodeq.core.types import DimensionResult


def test_parse_numeric_score_searches_anywhere():
    assert rg.parse_numeric_score("7.5/10") == 7.5
    assert rg.parse_numeric_score("x 7/10") == 7.0
    assert rg.parse_numeric_score("no score") is None
    assert rg.parse_numeric_score(None) is None


def test_grade_from_score_is_anchored():
    assert rg.grade_from_score("9.2/10") == "Exemplary"
    assert rg.grade_from_score("x 7/10") is None
    assert rg.grade_from_score("") is None


def test_most_frequent_grade_breaks_ties_on_rank():
    assert rg.most_frequent_grade(["Good", "Poor"]) == "Good"
    assert rg.most_frequent_grade([]) is None


def test_calculate_trend():
    assert rg.calculate_trend("8/10", "6/10") == "up"
    assert rg.calculate_trend("6/10", "8/10") == "down"
    assert rg.calculate_trend("6/10", "6/10") == "same"
    assert rg.calculate_trend(None, "6/10") == "none"


def test_summarize_dimensions_uses_numeric_average():
    summary = rg.summarize_dimensions([
        DimensionResult(dimension="security", overall_grade="Good", overall_score="8/10"),
    ])
    assert summary.overall_grade == "Good"


def test_old_paths_re_export_the_core_objects():
    from quodeq.analysis._report_scoring import grade_from_score as a
    from quodeq.data.fs.dimension_report.report_scoring import grade_from_score as b
    from quodeq.data.fs.report_parser.grades import (
        calculate_trend, most_frequent_grade, parse_numeric_score, summarize_dimensions,
    )
    assert a is b is rg.grade_from_score
    assert parse_numeric_score is rg.parse_numeric_score
    assert most_frequent_grade is rg.most_frequent_grade
    assert calculate_trend is rg.calculate_trend
    assert summarize_dimensions is rg.summarize_dimensions
