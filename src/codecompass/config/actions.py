from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from codecompass.bootstrap import DataProvider
from codecompass.config import generators
from codecompass.config import practices_manager
from codecompass.config.disciplines import get_discipline_language
from codecompass.config.dimensions import DIMENSION_NAMES
from codecompass.config.evaluators import build_evaluator_prompt
from codecompass.config.sources import has_required_sources_table

from codecompass.config.paths import ConfigPaths
from codecompass.logging import log_error
from codecompass.ports.data_errors import NotFoundError


@dataclass(frozen=True)
class ConfigureContext:
    paths: ConfigPaths
    max_parallel: int


def resolve_parallel(parallel: str | None, sequential: bool) -> int:
    if sequential:
        return 1
    if parallel is None:
        return 0
    return int(parallel)


def run_generate_evaluators(discipline: str, paths: ConfigPaths) -> int | None:
    if not discipline:
        log_error("--generate-maps requires a dimension name")
        return 1
    dimensions = [p.stem for p in paths.dimensions_dir.glob("*.json")]
    for dimension in dimensions:
        output_path = paths.evaluators_dir / discipline / f"{dimension}.json"
        prompt = build_evaluator_prompt(
            template_path=paths.prompts_dir / "dimension-mapper.md",
            discipline=discipline,
            dimension=dimension,
            practices_dir=paths.practices_dir / discipline,
            dimensions_dir=paths.dimensions_dir,
            output_path=output_path,
            date_value=date.today().isoformat(),
        )
        stdout, err = generators.run_ai_cli(prompt)
        if err:
            raise RuntimeError(err)
        output_path.write_text(stdout)


def run_generate_dimensions(paths: ConfigPaths) -> None:
    template = (paths.prompts_dir / "dimensions-generator.md").read_text()
    prompt = template.replace("{{DIMENSIONS}}", ", ".join(DIMENSION_NAMES))
    prompt = prompt.replace("{{OUTPUT_DIR}}", str(paths.dimensions_dir))
    prompt = prompt.replace("{{DATE}}", date.today().isoformat())
    stdout, err = generators.run_ai_cli(prompt)
    if err:
        raise RuntimeError(err)
    output_path = paths.dimensions_dir / "generated.json"
    output_path.write_text(stdout)


def run_generate_practices(
    discipline: str,
    paths: ConfigPaths,
    provider: DataProvider | None = None,
) -> int:
    if provider is None:
        from codecompass.bootstrap import default_provider
        provider = default_provider(paths.root)
    practices_repo = provider.practices
    try:
        topic_ids = practices_repo.list_topics(discipline)
    except NotFoundError as exc:
        log_error(str(exc))
        return 1
    if not topic_ids:
        log_error(f"No practice files found for discipline: {discipline}")
        return 1

    practices_dir = paths.practices_dir / discipline
    language = get_discipline_language(discipline, paths)
    if not language:
        log_error(f"Discipline not found in config: {discipline}")
        return 1
    topics: list[str] = []
    for topic_id in topic_ids:
        practice = practices_repo.get_practice(discipline, topic_id)
        metadata = practice.get("metadata", {}) if isinstance(practice, dict) else {}
        topic = metadata.get("topic") or topic_id
        topics.append(topic)
    practices_manager.generate_practices_for_discipline(
        discipline=discipline,
        language=language,
        topics=topics,
        output_dir=practices_dir,
        template_path=paths.prompts_dir / "principles-generator.md",
    )
    return 0


def add_discipline(name: str, language: str, category: str, paths: ConfigPaths) -> None:
    (paths.practices_dir / name).mkdir(parents=True, exist_ok=True)
    (paths.evaluators_dir / name).mkdir(parents=True, exist_ok=True)
    registry = paths.root / "config" / "disciplines.conf"
    registry.parent.mkdir(parents=True, exist_ok=True)
    content = registry.read_text() if registry.exists() else ""
    entry = f"[{name}]\nlanguage={language}\ncategory={category}\n"
    registry.write_text(content + entry)


def check_sources(discipline: str, paths: ConfigPaths) -> int:
    practices_dir = paths.practices_dir / discipline
    if not practices_dir.exists():
        log_error(f"Practices directory not found: {practices_dir}")
        return 1
    for practice_file in practices_dir.glob("*.md"):
        content = practice_file.read_text()
        if not has_required_sources_table(content):
            log_error(f"Missing sources table in {practice_file}")
            return 1
    return 0
