"""Builtin skill packs: markdown prompt fragments injected per turn."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

_logger = logging.getLogger(__name__)

_SKILLS_DIR = Path(
    os.environ.get(
        "QUODEQ_ASSISTANT_SKILLS_DIR",
        str(Path(__file__).resolve().parent.parent / "data" / "assistant" / "skills"),
    )
)

# Names the client answers locally; a skill file may never shadow them.
RESERVED_COMMANDS: tuple[tuple[str, str], ...] = (
    ("help", "Show what the assistant can do here"),
    ("skills", "List available skill commands"),
    ("actions", "List actions the assistant can draft"),
    ("clear", "Start a new conversation"),
)
_RESERVED_NAMES = frozenset(name for name, _ in RESERVED_COMMANDS)


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    instructions: str
    argument_hint: str = ""
    views: tuple[str, ...] = ()


def _parse(text: str) -> Skill | None:
    if not text.startswith("---"):
        return None
    try:
        _, front, body = text.split("---", 2)
    except ValueError:
        return None
    meta = {}
    for line in front.strip().splitlines():
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    if not meta.get("name") or not meta.get("description"):
        return None
    views = tuple(v.strip() for v in meta.get("views", "").split(",") if v.strip())
    return Skill(meta["name"], meta["description"], body.strip(),
                 argument_hint=meta.get("argument_hint", ""), views=views)


def load_skills(skills_dir: Path | None = None) -> dict[str, Skill]:
    directory = skills_dir or _SKILLS_DIR
    skills: dict[str, Skill] = {}
    if not directory.is_dir():
        return skills
    for path in sorted(directory.glob("*.md")):
        skill = _parse(path.read_text(encoding="utf-8"))
        if skill is None:
            _logger.warning("skipping malformed skill file: %s", path)
            continue
        if skill.name in _RESERVED_NAMES:
            _logger.warning("skill name %r is a reserved command; skipping %s",
                            skill.name, path)
            continue
        skills[skill.name] = skill
    return skills
