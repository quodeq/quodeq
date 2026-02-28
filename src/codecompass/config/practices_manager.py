from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from codecompass.config import generators
from codecompass.config.practice_renderer import write_practice_json
from codecompass.config.prompt_templates import render_template


def list_practice_names(discipline_dir: Path) -> list[str]:
    return sorted(path.stem for path in discipline_dir.glob("*.json") if path.is_file())


def _slugify(topic: str) -> str:
    return "".join(c.lower() if c.isalnum() else "_" for c in topic).strip("_")


def generate_practice_file(
    *,
    discipline: str,
    topic: str,
    language: str,
    output_dir: Path,
    template_path: Path,
) -> Path:
    template = template_path.read_text()
    today = date.today().isoformat()
    output_file = output_dir / f"{_slugify(topic)}.json"
    prompt = render_template(
        template,
        {
            "DISCIPLINE": discipline,
            "TOPIC": topic,
            "LANGUAGE": language,
            "DATE": today,
            "OUTPUT": str(output_file),
        },
    )
    stdout, err = generators.run_ai_cli(prompt)
    if err:
        raise RuntimeError(err)
    payload = json.loads(stdout)
    write_practice_json(output_file, payload)
    return output_file


def generate_practices_for_discipline(
    *,
    discipline: str,
    language: str,
    topics: list[str],
    output_dir: Path,
    template_path: Path,
) -> list[Path]:
    generated = []
    for topic in topics:
        generated.append(
            generate_practice_file(
                discipline=discipline,
                topic=topic,
                language=language,
                output_dir=output_dir,
                template_path=template_path,
            )
        )
    return generated
