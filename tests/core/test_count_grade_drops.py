"""count_grade_drops: the critical and major drop tables, scaled, the larger drop wins."""
from __future__ import annotations

import pytest

from quodeq.core.scoring.numerical import count_grade_drops


@pytest.mark.parametrize(("counts", "scale", "drops"), [
    ({}, 1, 0),
    ({"critical": 1}, 1, 1),
    ({"critical": 3}, 1, 1),
    ({"critical": 4}, 1, 2),
    ({"critical": 12}, 1, 3),
    ({"major": 3}, 1, 0),
    ({"major": 4}, 1, 1),
    ({"major": 12}, 1, 2),
    ({"major": 36}, 1, 3),
    ({"critical": 1, "major": 12}, 1, 2),
    ({"critical": 4, "major": 4}, 1, 2),
    ({"critical": 1}, 2, 0),
    ({"critical": 2}, 2, 1),
    ({"critical": 8}, 2, 2),
    ({"major": 7}, 2, 0),
    ({"major": 8}, 2, 1),
])
def test_drops(counts, scale, drops):
    assert count_grade_drops(counts, scale_multiplier=scale) == drops
