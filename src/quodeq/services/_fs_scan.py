"""Quick-scan service: extract project metadata without AI evaluation."""

from __future__ import annotations

import dataclasses
import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from quodeq.core.types.scan import ScanData

_logger = logging.getLogger(__name__)

# Directories to skip during file tree walk
_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".tox", "dist", "build", ".eggs"}
_GIT_TIMEOUT_S = 10

# Source-code extensions — kept in sync with `data/config/detection.json`
# (`extensions` map). Used to compute `code_files` so the wizard can show
# how many of the scanned files will actually be analysed by the eval.
_CODE_EXTENSIONS = frozenset({
    "py", "pyx", "ts", "tsx", "js", "jsx", "java", "kt", "kts", "swift", "m",
    "go", "rs", "rb", "php", "sh", "bash", "cs", "cpp", "c", "h", "scala",
    "dart", "ex", "exs", "r", "hs", "lhs", "lua", "jl", "zig", "ml", "mli",
    "cr", "pl", "pm",
})


def scan_project(project_dir: Path, *, output_dir: Path | None = None) -> ScanData:
    """Run a quick scan of a local project directory.

    Returns a ScanData with file tree, languages, branches, and modules.
    If *output_dir* is provided, writes the result to ``scan.json`` there.
    """
    project_dir = project_dir.resolve()
    file_tree: list[str] = []
    languages: dict[str, int] = {}
    code_file_count = 0

    for path in _walk_files(project_dir):
        # POSIX separators so the file_tree is consistent across platforms
        # (UI, scan.json consumers, and tests all assume "/").
        rel = path.relative_to(project_dir).as_posix()
        file_tree.append(rel)
        ext = path.suffix.lstrip(".")
        if ext:
            languages[ext] = languages.get(ext, 0) + 1
            if ext in _CODE_EXTENSIONS:
                code_file_count += 1

    branches = _list_branches(project_dir)
    modules = _list_modules(project_dir)
    scanned_at = datetime.now(timezone.utc).isoformat()

    result = ScanData(
        file_tree=sorted(file_tree),
        languages=languages,
        branches=branches,
        modules=modules,
        scanned_at=scanned_at,
        total_files=len(file_tree),
        code_files=code_file_count,
    )

    if output_dir is not None:
        _write_scan_json(result, output_dir)

    return result


def _walk_files(root: Path):
    """Walk directory tree iteratively, yielding file paths lazily.

    Uses a stack instead of recursion to avoid depth limits on deeply nested trees.
    Yields ``Path`` objects one at a time instead of accumulating into a list.
    """
    stack: list[Path] = [root]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir())
        except OSError:
            continue
        dirs: list[Path] = []
        for item in entries:
            if item.is_dir():
                if item.name not in _SKIP_DIRS and not item.name.startswith("."):
                    dirs.append(item)
            elif item.is_file():
                yield item
        # Push in reverse so alphabetical order is preserved via LIFO
        stack.extend(reversed(dirs))


def _list_branches(project_dir: Path) -> list[str]:
    """List local git branches, returning empty list if not a git repo."""
    if not (project_dir / ".git").exists():
        return []
    try:
        result = subprocess.run(
            ["git", "-C", str(project_dir), "branch", "--format=%(refname:short)"],
            capture_output=True, text=True, encoding="utf-8", timeout=_GIT_TIMEOUT_S,
        )
        if result.returncode != 0:
            return []
        return [b.strip() for b in result.stdout.splitlines() if b.strip()]
    except (subprocess.TimeoutExpired, OSError):
        _logger.debug("Failed to list git branches for %s", project_dir)
        return []


def _list_modules(project_dir: Path) -> list[str]:
    """Return top-level subdirectory names as module identifiers."""
    return sorted(
        d.name for d in project_dir.iterdir()
        if d.is_dir() and d.name not in _SKIP_DIRS and not d.name.startswith(".")
    )


def _write_scan_json(scan: ScanData, output_dir: Path) -> None:
    """Persist scan data as JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = dataclasses.asdict(scan)
    (output_dir / "scan.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
