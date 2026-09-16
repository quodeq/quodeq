"""A dismissal rescore recomputes density from the dimension's files_read."""
from quodeq.core.types.dimension import DimensionResult
from quodeq.core.types.finding import Finding
from quodeq.services.deleted import delete_finding, filter_deleted_from_dimensions
from quodeq.services.dismissed import dismiss_finding, filter_dismissed_from_dimensions
from quodeq.services.rescore import _rescore_dimension


def test_rescore_recomputes_density_from_files_read():
    violations = [
        Finding(practice_id="FT", verdict="violation", severity="major",
                req=f"R-{i}", file="a.py", line=i)
        for i in range(1, 5)
    ]
    dim = DimensionResult(dimension="reliability", violations=violations,
                          source_file_count=10, files_read=8)
    rescored = _rescore_dimension(dim, dismissed={("R-1", "a.py", 1)})
    assert rescored.totals.violation_count == 3
    assert rescored.totals.violations_per100_files == 37.5


def test_dismiss_filter_keeps_density(tmp_path):
    project_dir = tmp_path / "proj"
    violations = [
        Finding(practice_id="FT", verdict="violation", severity="major",
                req=f"R-{i}", file="a.py", line=i)
        for i in range(1, 5)
    ]
    dismiss_finding(project_dir, {"req": "R-1", "file": "a.py", "line": 1})
    dim = DimensionResult(dimension="reliability", violations=violations,
                          source_file_count=10, files_read=8)
    rescored = filter_dismissed_from_dimensions([dim], project_dir)[0]
    assert rescored.totals.violation_count == 3
    assert rescored.totals.violations_per100_files == 37.5


def test_delete_filter_keeps_density(tmp_path):
    project_dir = tmp_path / "proj"
    violations = [
        Finding(practice_id="FT", verdict="violation", severity="major",
                req=f"R-{i}", file=f"{letter}.py", line=i)
        for i, letter in enumerate(("a", "b", "c", "d"), start=1)
    ]
    delete_finding(project_dir, {"dimension": "reliability", "principle": "FT", "file": "d.py"})
    dim = DimensionResult(dimension="reliability", violations=violations,
                          source_file_count=10, files_read=8)
    rescored = filter_deleted_from_dimensions([dim], project_dir)[0]
    assert rescored.totals.violation_count == 3
    assert rescored.totals.violations_per100_files == 37.5
