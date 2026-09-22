"""violations_per_100_files(): one decimal, None when nothing was read."""
from quodeq.core.evidence.model import violations_per_100_files


def test_density_rounds_to_one_decimal():
    assert violations_per_100_files(273, 2259) == 12.1


def test_density_none_without_files():
    assert violations_per_100_files(5, 0) is None
    assert violations_per_100_files(5, None) is None
