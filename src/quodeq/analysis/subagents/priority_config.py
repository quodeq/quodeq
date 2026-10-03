"""Priority configuration loading and shared constants."""
from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass
from functools import lru_cache

from quodeq.config.paths import default_paths
from quodeq.core.observability import NULL_LOG, LogSink

_logger = logging.getLogger(__name__)

LANG_ALIASES = {"typescript": "javascript", "jsx": "javascript", "tsx": "javascript", "kotlin": "java"}

# Every key the priority modules read, with the values
# config/file_priority.json ships. A missing or partial file scores with
# these rather than raising KeyError on every file.
_DEFAULT_PRIORITY_CONFIG: dict = {
    "path_boost": {
        "src/": 5, "lib/": 5, "app/": 5, "core/": 5,
        "pkg/": 4, "internal/": 4,
        "test/": 1, "tests/": 1, "spec/": 1,
        "docs/": 0, "scripts/": 0, "tools/": 0,
    },
    "default_path_score": 2,
    "entry_points": ["main.*", "app.*", "index.*", "routes.*", "server.*"],
    "entry_point_boost": 3,
    "category_keywords": {
        "backend": ["controller", "service", "handler", "middleware", "router", "repository"],
        "mobile": ["activity", "fragment", "viewmodel", "screen", "widget", "composable"],
        "frontend": ["component", "page", "hook", "store", "reducer", "context"],
    },
    "category_keyword_boost": 2,
    "dimension_keywords": {
        "security": [
            "auth", "login", "crypto", "token", "session", "password", "secret", "sanitiz", "validat",
            "permission", "route", "handler", "middleware",
        ],
        "reliability": [
            "error", "exception", "retry", "fallback", "timeout", "recovery", "health", "monitor",
            "migration", "database", "circuit",
        ],
        "maintainability": [],
        "performance": ["cache", "query", "database", "pool", "batch", "stream", "index", "optimize", "buffer"],
        "flexibility": ["config", "plugin", "adapter", "factory", "interface", "abstract", "registry", "provider"],
        "usability": ["accessibility", "a11y", "i18n", "locale", "input", "form", "validation", "aria"],
    },
    "dimension_keyword_boost": 5,
    "maintainability_size_divisor": 2000,
    "fan_in_divisor": 3,
    "fan_in_max": 5,
    "git_churn_divisor": 4,
    "git_churn_max": 5,
    "git_recency_days": 14,
    "git_recency_multiplier": 1.5,
    "git_lookback_months": 3,
    "previous_violations_max": 5,
    "import_patterns": {
        "python": [r"^\s*(?:from|import)\s+(\S+)"],
        "javascript": [r"""(?:import|require)\s*\(?['"]([^'"]+)""", r"""from\s+['"]([^'"]+)"""],
        "java": [r"^\s*import\s+([\w.]+)"],
        "go": [r'"([^"]+)"'],
        "swift": [r"^\s*import\s+(\w+)"],
    },
}


@dataclass(frozen=True)
class ScoringInputs:
    """Grouped scoring parameters to reduce _score_files parameter count."""
    fan_in: dict[str, int]
    fan_in_divisor: int
    fan_in_max: int
    git_scores: dict[str, float]
    prev_violations: dict[str, int]
    max_prev_violations: int
    log: LogSink = NULL_LOG


@lru_cache(maxsize=1)
def load_priority_config() -> dict:
    """Load file priority config. Cached after first call."""
    config_path = default_paths().root / "config" / "file_priority.json"
    try:
        loaded = json.loads(config_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, PermissionError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        _logger.warning("Failed to load file_priority.json, using defaults: %s", exc)
        return copy.deepcopy(_DEFAULT_PRIORITY_CONFIG)
    if not isinstance(loaded, dict):
        _logger.warning("file_priority.json is not a JSON object, using defaults")
        return copy.deepcopy(_DEFAULT_PRIORITY_CONFIG)
    return {**copy.deepcopy(_DEFAULT_PRIORITY_CONFIG), **loaded}


def reset_priority_config_cache() -> None:
    """Clear the lru_cache on load_priority_config. Useful for test isolation."""
    load_priority_config.cache_clear()
