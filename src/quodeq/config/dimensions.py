"""Quality dimension codes and display helpers."""

from __future__ import annotations

DIMENSION_CODES = [
    ("aff", "affordability"),
    ("avl", "availability"),
    ("cfg", "configurability"),
    ("eff", "efficiency"),
    ("evo", "evolvability"),
    ("ext", "extensibility"),
    ("flx", "flexibility"),
    ("mnt", "maintainability"),
    ("perf", "performance"),
    ("rcv", "recoverability"),
    ("res", "resilience"),
    ("rob", "robustness"),
    ("scl", "scalability"),
    ("sim", "simplicity"),
    ("usx", "usability"),
]

DIMENSION_NAMES = [full for _, full in DIMENSION_CODES]


def render_dimension_table() -> str:
    """Return a human-readable table mapping shortcodes to dimension names."""
    lines = ["Dimension shortcodes:", ""]
    for code, full in DIMENSION_CODES:
        lines.append(f"  {code:<4} : {full}")
    lines.append("")
    lines.append("Usage: -d mnt,perf,scl   (select specific dimensions)")
    lines.append("       -d all             (select all dimensions)")
    return "\n".join(lines)
