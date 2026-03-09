from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from quodeq.config import generators
from quodeq.config.dimensions import DIMENSION_NAMES
from quodeq.config.evaluators import build_evaluator_prompt
from quodeq.config.sources import has_required_sources_table

from quodeq.config.paths import ConfigPaths
from quodeq.logging import log_error


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


def add_discipline(name: str, language: str, category: str, paths: ConfigPaths) -> None:
    (paths.evaluators_dir / name).mkdir(parents=True, exist_ok=True)
    registry = paths.root / "config" / "disciplines.conf"
    registry.parent.mkdir(parents=True, exist_ok=True)
    content = registry.read_text() if registry.exists() else ""
    entry = f"[{name}]\nlanguage={language}\ncategory={category}\n"
    registry.write_text(content + entry)


def run_refresh_practices(
    runtime: str,
    paths: ConfigPaths,
    *,
    min_stars: int = 500,
    dry_run: bool = False,
) -> int:
    from quodeq.config.knowledge_refresh import refresh_practices
    evaluators_dir = paths.root / "evaluators"
    return refresh_practices(runtime, evaluators_dir, min_stars=min_stars, dry_run=dry_run)


def run_refresh_analysis(
    runtime: str,
    paths: ConfigPaths,
    *,
    dry_run: bool = False,
) -> int:
    from quodeq.config.knowledge_refresh import refresh_analysis
    evaluators_dir = paths.root / "evaluators"
    return refresh_analysis(runtime, evaluators_dir, dry_run=dry_run)


def run_refresh_standards(paths: ConfigPaths, *, dry_run: bool = False) -> int:
    from quodeq.config.standards_fetcher import fetch_asvs_l1
    standards_dir = paths.root / "standards"
    count = fetch_asvs_l1(standards_dir, dry_run=dry_run)
    if not dry_run:
        print(f"Saved {count} ASVS L1 requirements to {standards_dir / 'asvs' / 'level1.json'}")
    return 0


def run_scaffold_plugin(runtime: str, paths: ConfigPaths) -> int:
    from quodeq.config.scaffold import scaffold_plugin
    evaluators_dir = paths.root / "evaluators"
    try:
        plugin_dir = scaffold_plugin(runtime, evaluators_dir)
        print(f"Created plugin skeleton at {plugin_dir}")
        return 0
    except ValueError as e:
        log_error(str(e))
        return 1


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
