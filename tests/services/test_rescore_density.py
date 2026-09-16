"""A dismissal rescore recomputes density from the dimension's files_read."""
from quodeq.core.types.dimension import DimensionResult
from quodeq.core.types.finding import Finding
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
    assert rescored.totals.violations_per_100_files == 37.5
