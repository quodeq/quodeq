from __future__ import annotations

from pathlib import Path

from codecompass.evaluate.lib.practices import list_practice_files
from codecompass.ports.practices import PracticesRepository


def resolve_selected_practice_names(all_practice_files: list[str], selected_indices: list[int]) -> list[str]:
    if not selected_indices:
        return list(all_practice_files)

    resolved: list[str] = []
    for index in selected_indices:
        if index < 1 or index > len(all_practice_files):
            raise ValueError(f"Practice index {index} out of range (1-{len(all_practice_files)})")
        resolved.append(all_practice_files[index - 1])
    return resolved


def build_practices_prompt(
    *,
    template: str,
    discipline: str,
    project_name: str,
    today: str,
    output_file: str,
    practices_list: str,
    practices_content: str,
) -> str:
    prompt = template
    prompt = prompt.replace("{{DISCIPLINE}}", discipline)
    prompt = prompt.replace("{{PRACTICES_LIST}}", practices_list)
    prompt = prompt.replace("{{REPO_NAME}}", project_name)
    prompt = prompt.replace("{{DATE}}", today)
    prompt = prompt.replace("{{OUTPUT_PATH}}", output_file)

    prompt += (
        "\n\n---\n\n# Practice Documents to Evaluate\n\n"
        "The following practice documents define the evaluation criteria. "
        "Assess the codebase against ALL practices defined in each document's Practices Index.\n\n"
        f"{practices_content}\n"
    )
    return prompt


def build_practices_evaluation(
    *,
    discipline: str,
    practices_repo: PracticesRepository,
    selected_indices: list[int],
    template: str,
    project_name: str,
    today: str,
    output_file: str,
) -> dict:
    all_practice_files = list_practice_files(practices_repo, discipline)
    if not all_practice_files:
        raise FileNotFoundError(f"No practice files found for discipline: {discipline}")

    selected_names = resolve_selected_practice_names(all_practice_files, selected_indices)

    practices_content = ""
    practices_list = ""

    for practice_name in selected_names:
        practice = practices_repo.get_practice(discipline, practice_name)
        body = practice.get("body", "") if isinstance(practice, dict) else ""
        if practices_list:
            practices_list = f"{practices_list}, {practice_name}"
        else:
            practices_list = practice_name
        practices_content += (
            "\n\n---\n\n"
            f"# Practice Document: {practice_name}\n\n"
            f"{body}\n"
        )

    prompt = build_practices_prompt(
        template=template,
        discipline=discipline,
        project_name=project_name,
        today=today,
        output_file=output_file,
        practices_list=practices_list,
        practices_content=practices_content,
    )

    return {
        "prompt": prompt,
        "practices_list": practices_list,
        "practices_content": practices_content,
        "output_file": output_file,
    }


def run_practices(
    *,
    discipline: str,
    practices_repo: PracticesRepository,
    template: str,
    project_name: str,
    today: str,
    output_file: Path,
    selected_indices: list[int],
) -> dict:
    result = build_practices_evaluation(
        discipline=discipline,
        practices_repo=practices_repo,
        selected_indices=selected_indices,
        template=template,
        project_name=project_name,
        today=today,
        output_file=str(output_file),
    )
    output_file.write_text(result["prompt"])
    return result
