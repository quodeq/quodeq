"""High-level configuration actions invoked by the CLI."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date

from quodeq.shared.ai_cli import run_ai_cli
from quodeq.config.dimensions import DIMENSION_NAMES
from quodeq.config.evaluators import EvaluatorContext, build_evaluator_prompt
from quodeq.config.prompt_templates import render_template
from quodeq.config.sources import has_required_sources_table

from quodeq.config.knowledge_refresh import refresh_analysis, refresh_practices
from quodeq.config.paths import ConfigPaths
from quodeq.config.scaffold import scaffold_plugin
from quodeq.config.standards_fetcher import fetch_asvs_l1
from quodeq.shared.logging import log_error
from quodeq.shared.utils import read_text, write_text

_GENERATED_DIMS_FILENAME = "generated.json"
_MAX_EVALUATOR_WORKERS = 8
_TPL_DIMENSIONS = "DIMENSIONS"
_TPL_OUTPUT_DIR = "OUTPUT_DIR"
_TPL_DATE = "DATE"


@dataclass(frozen=True)
class ConfigureContext:
    """Immutable bundle of paths and parallelism settings for a configure run."""
    paths: ConfigPaths
    max_parallel: int


def resolve_parallel(parallel: str | None, sequential: bool) -> int:
    """Determine the parallelism level from CLI flags."""
    if sequential:
        return 1
    if parallel is None:
        return 0
    return int(parallel)


def _generate_single_evaluator(
    discipline: str, dimension: str, paths: ConfigPaths, *, today: date | None = None,
) -> None:
    """Generate a single evaluator JSON file for one dimension."""
    output_path = paths.evaluators_dir / discipline / f"{dimension}.json"
    prompt = build_evaluator_prompt(
        template_path=paths.prompts_dir / "dimension-mapper.md",
        context=EvaluatorContext(
            discipline=discipline,
            dimension=dimension,
            practices_dir=paths.practices_dir / discipline,
            dimensions_dir=paths.dimensions_dir,
            output_path=output_path,
            date_value=(today or date.today()).isoformat(),
        ),
    )
    stdout, err = run_ai_cli(prompt)
    if err:
        raise RuntimeError(f"Evaluator generation failed for {dimension} → {output_path}: {err}")
    try:
        write_text(output_path, stdout)
    except OSError as exc:
        raise RuntimeError(f"Failed to write evaluator {output_path}: {exc}") from exc


def run_generate_evaluators(discipline: str, paths: ConfigPaths) -> int | None:
    """Generate evaluator JSON files for every dimension of a discipline."""
    if not discipline:
        log_error("--generate-maps requires a dimension name")
        return 1
    dimensions = [p.stem for p in paths.dimensions_dir.glob("*.json")]
    with ThreadPoolExecutor(max_workers=min(len(dimensions), _MAX_EVALUATOR_WORKERS)) as pool:
        futures = {
            pool.submit(_generate_single_evaluator, discipline, dim, paths): dim
            for dim in dimensions
        }
        for future in as_completed(futures):
            future.result()  # propagates any RuntimeError


def run_generate_dimensions(paths: ConfigPaths, *, today: date | None = None) -> None:
    """Generate dimension definitions via the AI CLI and save the output."""
    try:
        template = (paths.prompts_dir / "dimensions-generator.md").read_text()
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"Failed to read dimensions template: {exc}") from exc
    prompt = render_template(template, {
        _TPL_DIMENSIONS: ", ".join(DIMENSION_NAMES),
        _TPL_OUTPUT_DIR: str(paths.dimensions_dir),
        _TPL_DATE: (today or date.today()).isoformat(),
    })
    stdout, err = run_ai_cli(prompt)
    if err:
        raise RuntimeError(
            f"AI generation failed: {err}. Check your API key, network connection, "
            f"and AI provider configuration."
        )
    output_path = paths.dimensions_dir / _GENERATED_DIMS_FILENAME
    try:
        write_text(output_path, stdout)
    except OSError as exc:
        raise RuntimeError(f"Failed to write dimensions output to {output_path}: {exc}") from exc


def add_discipline(name: str, language: str, category: str, paths: ConfigPaths) -> None:
    """Register a new discipline by creating its directory and config entry."""
    (paths.evaluators_dir / name).mkdir(parents=True, exist_ok=True)
    registry = paths.disciplines_conf
    registry.parent.mkdir(parents=True, exist_ok=True)
    content = registry.read_text() if registry.exists() else ""
    entry = f"[{name}]\nlanguage={language}\ncategory={category}\n"
    try:
        registry.write_text(content + entry)
    except OSError as exc:
        raise RuntimeError(f"Failed to write discipline config to {registry}: {exc}") from exc


def run_refresh_practices(
    runtime: str,
    paths: ConfigPaths,
    *,
    min_stars: int = 500,
    dry_run: bool = False,
) -> int:
    """Refresh practices data for a plugin runtime from GitHub cursor-rules."""
    evaluators_dir = paths.evaluators_dir
    return refresh_practices(runtime, evaluators_dir, min_stars=min_stars, dry_run=dry_run)


def run_refresh_analysis(
    runtime: str,
    paths: ConfigPaths,
    *,
    dry_run: bool = False,
) -> int:
    """Refresh analysis data for a plugin runtime from linter documentation."""
    evaluators_dir = paths.evaluators_dir
    return refresh_analysis(runtime, evaluators_dir, dry_run=dry_run)


def run_refresh_standards(paths: ConfigPaths, *, dry_run: bool = False) -> int:
    """Re-fetch OWASP ASVS Level 1 requirements into the standards directory."""
    standards_dir = paths.root / "standards"
    count = fetch_asvs_l1(standards_dir, dry_run=dry_run)
    if not dry_run:
        print(f"Saved {count} ASVS L1 requirements to {standards_dir / 'asvs' / 'level1.json'}")
    return 0


def run_scaffold_plugin(runtime: str, paths: ConfigPaths) -> int:
    """Create a new plugin skeleton directory for the given runtime."""
    evaluators_dir = paths.evaluators_dir
    try:
        plugin_dir = scaffold_plugin(runtime, evaluators_dir)
        print(f"Created plugin skeleton at {plugin_dir}")
        return 0
    except ValueError as e:
        log_error(str(e))
        return 1


def check_sources(discipline: str, paths: ConfigPaths) -> int:
    """Verify that every practice file in a discipline has a sources table."""
    practices_dir = paths.practices_dir / discipline
    if not practices_dir.exists():
        log_error(f"Practices directory not found: {practices_dir}")
        return 1
    for practice_file in practices_dir.glob("*.md"):
        content = read_text(practice_file)
        if not has_required_sources_table(content):
            log_error(f"Missing sources table in {practice_file}")
            return 1
    return 0
