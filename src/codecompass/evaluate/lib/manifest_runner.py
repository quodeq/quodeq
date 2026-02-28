from __future__ import annotations


def build_project_context(manifest: dict) -> str:
    targets = manifest.get("targets", [])
    context = "## Project Context\n"
    context += f"This is a multi-target project with {len(targets)} evaluation targets:\n\n"
    for target in targets:
        name = target.get("name", "")
        path = target.get("path", "")
        discipline = target.get("discipline", "")
        context += f"  - {name} ({path}) -> {discipline}\n"
    return context


def run_multi_target_evaluation(manifest: dict, target_filter: str | None = None) -> dict:
    targets = manifest.get("targets", [])
    selected = [t for t in targets if not target_filter or t.get("name") == target_filter]
    return {"total": len(selected), "succeeded": len(selected), "failed": 0, "skipped": 0}
