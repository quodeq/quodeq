"""Load DisciplineRule instances from an INI-style .conf file."""

from __future__ import annotations

import logging
from pathlib import Path

from quodeq.shared.utils import read_text

from quodeq.config._discipline_rule import DisciplineRule
from quodeq.config._discipline_parser import parse_fields

_logger = logging.getLogger(__name__)


def load_disciplines_from_file(path: Path) -> tuple[dict[str, DisciplineRule], list[str]]:
    """Parse an INI-style disciplines.conf file into ``(rules, problems)``.

    *problems* is a list of human-readable strings describing parse-time issues
    (currently: unknown keys). The caller decides whether to log them or raise
    based on its strictness setting.
    """
    sections: dict[str, list[tuple[str, str]]] = {}
    current_name: str | None = None
    try:
        lines = read_text(path).splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(
            f"Cannot read disciplines config {path}: {exc}. "
            f"Check file permissions or run 'quodeq configure' to regenerate."
        ) from exc
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current_name = line[1:-1]
            sections[current_name] = []
            continue
        if current_name is None or "=" not in line:
            continue
        key, value = line.split("=", 1)
        sections[current_name].append((key.strip(), value.strip()))

    rules: dict[str, DisciplineRule] = {}
    problems: list[str] = []
    for name, kvs in sections.items():
        kwargs, unknown = parse_fields(kvs)
        for key in unknown:
            problems.append(f"section [{name}]: unknown key {key!r} (typo? — ignored)")
        rules[name] = DisciplineRule(name=name, **kwargs)
    return rules, problems
