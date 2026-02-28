from __future__ import annotations

from pathlib import Path

SCAN_SKIP_DIRS = {
    "node_modules",
    "dist",
    "build",
    "vendor",
    ".git",
    ".claude",
    ".next",
    "__pycache__",
    ".gradle",
    "Pods",
}


def _detect_discipline(check_dir: Path) -> str | None:
    if (check_dir / "next.config.js").is_file():
        return "frontend_nextjs"
    if (check_dir / "package.json").is_file():
        return "frontend_react"
    if (check_dir / "pom.xml").is_file():
        return "backend_springboot_java"
    if (check_dir / "build.gradle").is_file() or (check_dir / "build.gradle.kts").is_file():
        return "backend_springboot_kotlin"
    return None


def _build_manifest(project_name: str, targets: list[dict]) -> dict:
    return {
        "version": 1,
        "project": {"name": project_name},
        "targets": targets,
    }


def scan_project(repo_dir: str) -> dict:
    repo_path = Path(repo_dir)
    project_name = repo_path.name

    root_discipline = _detect_discipline(repo_path)
    if root_discipline:
        return _build_manifest(
            project_name,
            [
                {
                    "name": project_name,
                    "path": ".",
                    "discipline": root_discipline,
                    "dimensions": "all",
                }
            ],
        )

    targets: list[dict] = []
    for subdir in repo_path.iterdir():
        if not subdir.is_dir():
            continue
        if subdir.name in SCAN_SKIP_DIRS:
            continue

        discipline = _detect_discipline(subdir)
        if discipline:
            targets.append(
                {
                    "name": subdir.name,
                    "path": subdir.name,
                    "discipline": discipline,
                    "dimensions": "all",
                }
            )
            continue

        for sub2 in subdir.iterdir():
            if not sub2.is_dir():
                continue
            if sub2.name in SCAN_SKIP_DIRS:
                continue
            discipline = _detect_discipline(sub2)
            if discipline:
                rel_path = f"{subdir.name}/{sub2.name}"
                targets.append(
                    {
                        "name": sub2.name,
                        "path": rel_path,
                        "discipline": discipline,
                        "dimensions": "all",
                    }
                )

    return _build_manifest(project_name, targets)
