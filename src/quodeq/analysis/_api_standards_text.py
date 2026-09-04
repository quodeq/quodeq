"""Source-file gathering and compiled-standards text for the API prompt.

Split out of subprocess.py: repository scanning that selects which source
files get inlined into a direct-API prompt, and rendering compiled standards
JSON into the compact grouped-JSON text sent to API models. None of these
functions are mock.patch targets.
"""
from __future__ import annotations

import json as _json
import logging
import os
from pathlib import Path

from quodeq.analysis import dispatch_policy

_log = logging.getLogger(__name__)


def _load_skip_dirs() -> frozenset[str]:
    """Load skip_dirs from detection.json (shared with manifest builder)."""
    try:
        det_path = Path(__file__).resolve().parent.parent / "data" / "config" / "detection.json"
        data = _json.loads(det_path.read_text(encoding="utf-8"))
        return frozenset(data.get("skip_dirs", []))
    except (OSError, _json.JSONDecodeError):
        return frozenset({"node_modules", ".git", "__pycache__", "venv", ".venv", "dist", "build"})


_SKIP_DIRS = _load_skip_dirs()
# Code files first, style/markup last
_CODE_EXTS = frozenset({".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".rb", ".php", ".c", ".cpp", ".h", ".cs", ".swift", ".kt"})
_MARKUP_EXTS = frozenset({".html", ".css", ".scss", ".vue", ".svelte"})


def _gather_source_files(work_dir: Path) -> list[Path]:
    """Collect source files from work_dir for API prompt assembly.

    Prioritizes code files over markup/styles and caps total size to
    fit within local model context limits.
    """
    _ALL_EXTS = _CODE_EXTS | _MARKUP_EXTS
    all_files: list[Path] = [
        f for f in work_dir.rglob("*") if f.is_file() and f.suffix in _ALL_EXTS
    ]
    # Cache stat results to avoid repeated syscalls on the same files
    stat_cache: dict[Path, int] = {}
    for f in all_files:
        try:
            stat_cache[f] = f.stat().st_size
        except OSError:
            pass

    # Filter out non-source dirs, dotdirs, empty files, and oversized files
    filtered = [
        f for f in all_files
        if f in stat_cache
        and not any(p in f.parts for p in _SKIP_DIRS)
        and not any(p.startswith(".") for p in f.relative_to(work_dir).parts)
        and 0 < stat_cache[f] < dispatch_policy.api_file_size_cap()
    ]
    # Prioritize code files over markup
    code_files = [f for f in filtered if f.suffix in _CODE_EXTS]
    markup_files = [f for f in filtered if f.suffix in _MARKUP_EXTS]
    # Within each group, sort by size (moderate files first — not too small, not too big)
    code_files.sort(key=lambda f: stat_cache[f], reverse=True)
    markup_files.sort(key=lambda f: stat_cache[f], reverse=True)

    # Fill up to the prompt char budget
    selected: list[Path] = []
    total_chars = 0
    for f in code_files + markup_files:
        size = stat_cache[f]
        if total_chars + size > _api_prompt_char_budget():
            continue
        selected.append(f)
        total_chars += size

    _log.debug("Selected %d files (%d chars) from %d candidates for API prompt",
              len(selected), total_chars, len(filtered))
    return selected


_DEFAULT_MAX_API_PROMPT_CHARS = 30000  # Target inlined-file budget for local models (~8K tokens)


def _api_prompt_char_budget(env: dict[str, str] | None = None) -> int:
    """Max bytes of file content to inline per model call.

    *env* lets subprocess.py pass the process environment explicitly so
    this analysis-layer function doesn't read os.environ unprompted; also
    raised together with QUODEQ_MAX_API_FILE_SIZE for larger-context models.
    """
    raw = (env or os.environ).get("QUODEQ_MAX_API_PROMPT_CHARS", "")
    try:
        return int(raw) if raw else _DEFAULT_MAX_API_PROMPT_CHARS
    except ValueError:
        return _DEFAULT_MAX_API_PROMPT_CHARS


_DEFAULT_MAX_STANDARDS_CHARS = 50000  # Allow full standards for models with large context


def _max_standards_chars(env: dict[str, str] | None = None) -> int:
    """Max chars of standards text to include in an API prompt.

    Read per call (not at import) so QUODEQ_MAX_STANDARDS_CHARS can be
    raised together with QUODEQ_MAX_API_PROMPT_CHARS / QUODEQ_CONTEXT_SIZE
    when running larger-context models. Malformed values fall back to the
    default instead of raising.
    """
    raw = (env or os.environ).get("QUODEQ_MAX_STANDARDS_CHARS", "")
    try:
        return int(raw) if raw else _DEFAULT_MAX_STANDARDS_CHARS
    except ValueError:
        return _DEFAULT_MAX_STANDARDS_CHARS


def _load_standards_text(
    compiled_dir: Path | None,
    dimension: str | None,
    overrides: dict | None = None,
    *,
    max_chars: int | None = None,
) -> str:
    """Load compiled standards as structured JSON for the API prompt.

    Renders from the compiled JSON as a compact JSON array grouped by principle,
    so API models see explicit structure instead of a flat requirement list.
    Falls back to the .md file if JSON is unavailable.

    *overrides* is the per-project threshold override map from
    :func:`quodeq.core.standards.overrides.load_project_overrides`.  When
    supplied, placeholder templates in requirement text are resolved before
    the text is sent to the model.

    Truncates to *max_chars* (default :func:`_max_standards_chars`) to keep
    prompts within context limits.
    """
    limit = max_chars if max_chars is not None else _max_standards_chars()
    if not compiled_dir or not dimension:
        return ""
    json_path = compiled_dir / f"{dimension}.json"
    if json_path.exists():
        try:
            data = _json.loads(json_path.read_text(encoding="utf-8"))
            text = _render_standards_grouped(data, overrides=overrides)
            if text:
                if len(text) > limit:
                    _log.info("Truncating %s standards from %d to %d chars for API prompt",
                              dimension, len(text), limit)
                    text = text[:limit] + "\n\n[... standards truncated for context limits ...]"
                return text
        except (OSError, _json.JSONDecodeError):
            pass
    md_path = compiled_dir / f"{dimension}.md"
    if md_path.exists():
        try:
            text = md_path.read_text(encoding="utf-8")
            if len(text) > limit:
                text = text[:limit] + "\n\n[... standards truncated for context limits ...]"
            return text
        except OSError:
            pass
    return ""


def _render_standards_grouped(data: dict, overrides: dict | None = None) -> str:
    """Render standards as a compact JSON array grouped by principle.

    The explicit structure helps local models give attention to ALL principle
    groups instead of fixating on the first ones in a flat list.

    *overrides* is the per-project ``{req_id: {param: value}}`` map produced
    by :func:`quodeq.core.standards.overrides.load_project_overrides`.  When
    present, each requirement's text template is resolved before being emitted
    so that models never receive raw ``{placeholder}`` strings.
    """
    from quodeq.core.standards.overrides import resolve_requirement_text  # noqa: PLC0415

    principles = data.get("principles", [])
    if not principles:
        return ""
    checklist = []
    for p in principles:
        checklist.append({
            "principle": p.get("name", "Unknown"),
            "requirements": [
                {"id": r["id"], "rule": resolve_requirement_text(r, (overrides or {}).get(r["id"]))}
                for r in p.get("requirements", [])
            ],
        })
    return _json.dumps(checklist, separators=(",", ":"))
