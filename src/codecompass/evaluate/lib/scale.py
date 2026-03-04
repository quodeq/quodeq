from __future__ import annotations

# Project size tiers — (min_source_files, multiplier)
#        Small (<500) x1 | Medium (500-5k) x2 | Large (5k-20k) x3
#        XLarge (20k-50k) x4 | XXLarge (50k-100k) x5 | Enterprise (100k+) x6
_SCALE_TIERS: list[tuple[int, int]] = [
    (100_000, 6),
    ( 50_000, 5),
    ( 20_000, 4),
    (  5_000, 3),
    (    500, 2),
    (      0, 1),
]


SCALE_TIER_NAMES: dict[int, str] = {
    1: "Small",
    2: "Medium",
    3: "Large",
    4: "XLarge",
    5: "XXLarge",
    6: "Enterprise",
}


def scale_multiplier(source_file_count: int) -> int:
    """Return the size-based scaling multiplier for a project."""
    for threshold, multiplier in _SCALE_TIERS:
        if source_file_count >= threshold:
            return multiplier
    return 1
