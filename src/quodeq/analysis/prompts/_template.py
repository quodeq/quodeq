"""Template loading and hashing utilities."""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from quodeq.config.paths import default_paths

_TEMPLATE_HASH_CACHE_SIZE = 128


def load_template(
    template_path: Path | None = None,
    *,
    prompts_dir: Path | None = None,
    template_name: str = "compass.md",
) -> str:
    """Load a prompt template.

    Args:
        template_path: Explicit path to a template file (takes priority).
        prompts_dir: Directory containing prompt templates; used to locate
            *template_name* when *template_path* is not given.
        template_name: Template filename to load (default ``compass.md``).
    """
    if template_path:
        try:
            return template_path.read_text()
        except (OSError, UnicodeDecodeError) as exc:
            raise FileNotFoundError(f"Cannot read template {template_path}: {exc}") from exc
    if prompts_dir is None:
        prompts_dir = default_paths().prompts_dir
    path = prompts_dir / template_name
    try:
        return path.read_text()
    except (OSError, UnicodeDecodeError) as exc:
        raise FileNotFoundError(f"Cannot read template {path}: {exc}") from exc


@lru_cache(maxsize=_TEMPLATE_HASH_CACHE_SIZE)
def template_hash(template: str) -> str:
    """Return a short hash of the template string, computed once per unique template."""
    return hashlib.sha256(template.encode()).hexdigest()[:12]
