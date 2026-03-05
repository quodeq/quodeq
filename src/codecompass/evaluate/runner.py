from __future__ import annotations

import json
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from codecompass.bootstrap import DataProvider
from codecompass.config.paths import ConfigPaths, default_paths
from codecompass.evaluate.lib.ai_cli import run_ai_cli
from codecompass.evaluate.lib.common import fail_with_error, log_banner, log_info, log_step, log_success, log_warning
from codecompass.evaluate.lib.dimension_runner import DimensionRunContext, run_dimensions
from codecompass.evaluate.lib.dimensions import list_available_dimensions, resolve_dimension_selection
from codecompass.evaluate.lib.discipline_detector import (
    DisciplineDetectionError,
    detect_discipline,
)
from codecompass.evaluate.lib.evaluation import compute_prompt_hash
from codecompass.evaluate.lib.practices_runner import build_practices_evaluation
from codecompass.evaluate.lib.prescan import run_prescan_metrics
from codecompass.evaluate.lib.progress import format_end, format_start
from codecompass.evaluate.lib.repo_handler import prepare_repository
from codecompass.ports.data_errors import NotFoundError
from codecompass.utils import is_repo_url


@dataclass(frozen=True)
class EvaluateConfig:
    discipline: str | None
    repo: str | None
    reports_dir: Path
    reports_defaulted: bool
    dimensions: list[str] = field(default_factory=list)
    evidence_only: bool = False
    no_prescan: bool = False
    numerical: bool = False
    version: str | None = None
    provider: DataProvider | None = None


def ensure_reports_dir(reports_dir: Path, reports_defaulted: bool) -> None:
    if reports_dir.exists():
        return
    if reports_defaulted:
        reports_dir.mkdir(parents=True, exist_ok=True)
        return
    raise FileNotFoundError(
        "Reports directory not found. "
        "Run `mkdir -p <path>` or omit --reports to use the default."
    )


def _get_codecompass_version() -> str:
    try:
        result = subprocess.run(
            ["git", "describe", "--tags"],
            cwd=str(Path(__file__).parent),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


def _parse_source_file_count(prescan_summary: str) -> int:
    for line in prescan_summary.splitlines():
        if line.startswith("Files:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except (ValueError, IndexError):
                pass
    return 0


from codecompass.evaluate.project_resolver import resolve_project_uuid as resolve_project_uuid  # re-export


def _resolve_repo_path(repo: str) -> tuple[str | None, int | None]:
    """Resolve to a local path, cloning if needed. Returns (path, error_code)."""
    if is_repo_url(repo):
        try:
            return prepare_repository(repo), None
        except Exception as exc:
            return None, fail_with_error(str(exc))
    local = Path(repo).resolve()
    if not local.exists():
        return None, fail_with_error(f"Local path {local} does not exist")
    return str(local), None


def _resolve_discipline_and_dimensions(
    config: EvaluateConfig, paths: ConfigPaths,
) -> tuple[EvaluateConfig, DataProvider | None, list[str] | None, int | None]:
    """Detect discipline (if needed) and resolve dimension selection."""
    if not config.discipline:
        try:
            config = EvaluateConfig(
                discipline=detect_discipline(config.repo),
                repo=config.repo,
                reports_dir=config.reports_dir,
                reports_defaulted=config.reports_defaulted,
                dimensions=config.dimensions,
                evidence_only=config.evidence_only,
                no_prescan=config.no_prescan,
                numerical=config.numerical,
                version=config.version,
            )
        except DisciplineDetectionError as exc:
            return config, None, None, fail_with_error(str(exc))

    if config.provider is not None:
        provider = config.provider
    else:
        from codecompass.bootstrap import default_provider
        provider = default_provider(paths.vroot)
    try:
        available = list_available_dimensions(provider.evaluators, config.discipline)
    except NotFoundError:
        return config, None, None, fail_with_error("discipline missing or evaluators directory absent")
    try:
        selected, skipped = resolve_dimension_selection(config.dimensions or ["all"], available)
    except ValueError as exc:
        return config, None, None, fail_with_error(str(exc))
    if skipped:
        log_warning(f"Skipped (not available for {config.discipline}): {', '.join(skipped)}")
    return config, provider, selected, None


def _load_templates(paths: ConfigPaths) -> tuple[str, str, str, str] | int:
    """Load and hash analysis/scoring templates. Returns tuple or error code."""
    analysis_path = paths.prompts_dir / "analysis.md"
    scoring_path = paths.prompts_dir / "scoring.md"
    if not analysis_path.exists():
        return fail_with_error(f"Analysis template not found: {analysis_path}")
    if not scoring_path.exists():
        return fail_with_error(f"Scoring template not found: {scoring_path}")
    analysis_template = analysis_path.read_text()
    scoring_template = scoring_path.read_text()
    return analysis_template, scoring_template, compute_prompt_hash(analysis_template), compute_prompt_hash(scoring_template)


def _run_prescan(config: EvaluateConfig) -> tuple[str, int]:
    """Run prescan if enabled. Returns (metrics_text, source_file_count)."""
    if config.no_prescan:
        return "", 0
    log_step("Scanning repository")
    prescan_summary = run_prescan_metrics(config.repo, config.discipline)
    source_file_count = _parse_source_file_count(prescan_summary)
    log_success(f"{source_file_count:,} source files")
    return prescan_summary, source_file_count


def _resolve_project_metadata(
    config: EvaluateConfig, repo_path: str,
) -> tuple[str, str, str, str]:
    """Derive project identity fields. Returns (today, run_id, project_name, project_uuid)."""
    today = datetime.now().isoformat(timespec='seconds')
    run_id = str(uuid.uuid4())
    project_name = config.repo.split("/")[-1].replace(".git", "") if is_repo_url(config.repo) else Path(config.repo).name
    location = "online" if is_repo_url(config.repo) else "local"
    project_uuid = resolve_project_uuid(config.reports_dir, project_name, repo_path, config.discipline, location=location)
    return today, run_id, project_name, project_uuid


def _create_run_directories(
    reports_dir: Path, project_uuid: str, run_id: str,
) -> tuple[Path, Path]:
    """Create and return (evidence_dir, evaluation_dir)."""
    evidence_dir = reports_dir / project_uuid / run_id / "evidence"
    evaluation_dir = reports_dir / project_uuid / run_id / "evaluation"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    return evidence_dir, evaluation_dir


def run(config: EvaluateConfig) -> int:
    if not config.repo:
        return fail_with_error("repository path required")

    ensure_reports_dir(config.reports_dir, config.reports_defaulted)

    repo_path, err = _resolve_repo_path(config.repo)
    if err is not None:
        return err

    paths = default_paths(version=config.version)
    config, provider, selected, err = _resolve_discipline_and_dimensions(config, paths)
    if err is not None:
        return err

    today, run_id, project_name, project_uuid = _resolve_project_metadata(config, repo_path)

    dim_label = ", ".join(selected) if len(selected) <= 4 else f"{len(selected)} dimensions"
    log_banner([
        "CodeCompass Evaluation",
        f"Repo: {project_name}  ·  Discipline: {config.discipline}  ·  {dim_label}",
    ])

    evidence_dir, evaluation_dir = _create_run_directories(config.reports_dir, project_uuid, run_id)
    log_info(f"Report path: {evaluation_dir}")

    templates = _load_templates(paths)
    if isinstance(templates, int):
        return templates
    analysis_template, scoring_template, analysis_hash, scoring_hash = templates

    prescan_metrics, source_file_count = _run_prescan(config)

    ctx = DimensionRunContext(
        work_dir=repo_path,
        discipline=config.discipline,
        project_name=project_name,
        today=today,
        evidence_dir=evidence_dir,
        evaluation_dir=evaluation_dir,
        evaluators_dir=paths.evaluators_dir,
        analysis_template=analysis_template,
        scoring_template=scoring_template,
        analysis_hash=analysis_hash,
        scoring_hash=scoring_hash,
        source_file_count=source_file_count,
        prescan_metrics=prescan_metrics,
        codecompass_version=_get_codecompass_version(),
        evidence_only=config.evidence_only,
        numerical=config.numerical,
    )

    _success, failed = run_dimensions(selected, ctx)
    return 0 if failed == 0 else 1


def run_practices_mode(
    *,
    repo_path: str,
    discipline: str,
    provider: DataProvider,
    template_path: Path,
    output_file: Path,
    selected_indices: list[int],
    today: str | None = None,
    no_prescan: bool = False,
) -> int:
    repo_root = Path(repo_path)
    project_name = repo_root.name
    date_value = today or datetime.now().isoformat(timespec='seconds')

    template = template_path.read_text()

    result = build_practices_evaluation(
        discipline=discipline,
        practices_repo=provider.practices,
        template=template,
        project_name=project_name,
        today=date_value,
        output_file=str(output_file),
        selected_indices=selected_indices,
    )

    prompt = result["prompt"]

    if not no_prescan:
        log_info(format_start("prescan"))
        prescan_summary = run_prescan_metrics(str(repo_root), discipline)
        log_info(format_end("prescan"))
        prompt = f"{prompt}\n\n---\n\n# Prescan Summary\n\n{prescan_summary}"

    log_info(format_start("ai"))
    ai_output, ai_error = run_ai_cli(prompt)
    log_info(format_end("ai"))

    if ai_error:
        return fail_with_error(ai_error)

    output_file.write_text(ai_output or "")
    return 0
