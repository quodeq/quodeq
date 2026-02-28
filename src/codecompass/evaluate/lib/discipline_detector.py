from __future__ import annotations

from pathlib import Path

from codecompass.config.discipline_registry import DisciplineRegistry
from codecompass.config.paths import default_paths
from codecompass.evaluate.lib.manifest import (
    manifest_exists,
    manifest_path,
    parse_manifest_target_core_fields,
    parse_manifest_target_count,
)
from codecompass.logging import log_warning


class DisciplineDetectionError(RuntimeError):
    pass


def _load_registry() -> DisciplineRegistry:
    conf = default_paths().root / "config" / "disciplines.conf"
    return DisciplineRegistry.from_file(conf)


def detect_from_manifest(repo_dir: str) -> str | None:
    if not manifest_exists(repo_dir):
        return None
    path = manifest_path(repo_dir)
    count = parse_manifest_target_count(path)
    if count != 1:
        raise DisciplineDetectionError(
            "Manifest contains multiple targets; select a specific target for evaluation."
        )
    _, _, discipline = parse_manifest_target_core_fields(path, 0)
    if discipline:
        return discipline
    raise DisciplineDetectionError("Manifest target missing discipline.")


def detect_from_rules(repo_dir: str) -> str | None:
    registry = _load_registry()
    matches = registry.detect_matches(Path(repo_dir))
    if not matches:
        return None
    if len(matches) > 1:
        chosen = registry.choose_highest_priority(matches)
        log_warning(f"Multiple disciplines detected: {', '.join(matches)}. Using {chosen}.")
        return chosen
    return matches[0]


def detect_discipline(repo_dir: str) -> str:
    detected = detect_from_manifest(repo_dir)
    if detected:
        return detected
    detected = detect_from_rules(repo_dir)
    if detected:
        return detected
    raise DisciplineDetectionError(
        "Unable to detect discipline. Add one to config/disciplines.conf or pass it explicitly."
    )
