"""Refresh pipeline for AI analysis guidance and engineering practices from GitHub."""
from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path

from quodeq.shared.ai_cli import run_ai_cli
from quodeq.config.prompt_templates import render_template
from quodeq.shared.logging import log_error, log_info, log_success, log_warning
from quodeq.shared.utils import get_github_raw_base_url, get_github_search_url, show_diff

# Per-runtime linter documentation sources
_LINTER_SOURCES_PATH = Path(__file__).parent / "linter_sources.json"
_REFRESH_TEMPLATES_DIR = Path(__file__).parent / "refresh_templates"
_FETCH_TIMEOUT_S = 15
_CONTENT_SAMPLE_LIMIT = 4000
_MAX_FETCH_WORKERS = 8
_LINTER_DOCS_LIMIT = 6000
_EXISTING_CONTENT_LIMIT = 2000


@lru_cache(maxsize=1)
def _get_linter_sources() -> dict[str, str]:
    return json.loads(_LINTER_SOURCES_PATH.read_text())


def refresh_practices(
    runtime: str,
    evaluators_dir: Path,
    *,
    min_stars: int = 500,
    dry_run: bool = False,
) -> int:
    """Refresh practices.json for a runtime by curating GitHub cursor rules via LLM.

    Fetches top-starred cursor-rules repos for the runtime, extracts content,
    and uses the LLM to produce a practices.json with bad/good examples.
    Returns 0 on success, 1 on error.
    """
    out_path = evaluators_dir / runtime / "knowledge" / "practices.json"

    repos = _fetch_cursor_rules_repos(runtime, min_stars)
    if not repos:
        log_warning(f"No cursor-rules repos found for runtime={runtime!r} with min_stars={min_stars}")
        return 1

    content_samples = _fetch_repo_content(repos[:3])
    if not content_samples:
        log_error("Could not fetch content from any repo")
        return 1

    prompt = _build_practices_prompt(runtime, content_samples, out_path)
    stdout, err = run_ai_cli(prompt)
    if err:
        log_error(f"LLM error: {err}")
        return 1

    try:
        payload = json.loads(stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        log_error(f"LLM returned invalid JSON: {exc}")
        return 1

    new_content = json.dumps(payload, indent=2)
    if dry_run:
        count = len(payload.get("practices", []))
        log_info(f"[dry-run] Would write {count} practices to {out_path}")
        show_diff(out_path, new_content)
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(new_content)
    log_success(f"Written {len(payload.get('practices', []))} practices to {out_path}")
    return 0


def refresh_analysis(
    runtime: str,
    evaluators_dir: Path,
    *,
    dry_run: bool = False,
) -> int:
    """Refresh analysis.md for a runtime from official linter docs via LLM.

    Returns 0 on success, 1 on error.
    """
    out_path = evaluators_dir / runtime / "knowledge" / "analysis.md"

    linter_sources = _get_linter_sources()
    source_url = linter_sources.get(runtime)
    if not source_url:
        log_warning(f"No linter source configured for runtime={runtime!r}")
        log_info(f"Supported runtimes: {', '.join(sorted(linter_sources))}")
        return 1

    linter_docs = _fetch_url(source_url)
    if not linter_docs:
        log_error(f"Could not fetch linter docs from {source_url}")
        return 1

    prompt = _build_analysis_prompt(runtime, linter_docs, out_path)
    stdout, err = run_ai_cli(prompt)
    if err:
        log_error(f"LLM error: {err}")
        return 1

    if dry_run:
        log_info(f"[dry-run] Would write analysis.md to {out_path}")
        show_diff(out_path, stdout)
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(stdout)
    log_success(f"Written analysis.md to {out_path}")
    return 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_cursor_rules_repos(runtime: str, min_stars: int) -> list[dict]:
    query = urllib.parse.urlencode({
        "q": f"cursor-rules {runtime}",
        "sort": "stars",
        "order": "desc",
        "per_page": "10",
    })
    url = f"{get_github_search_url()}?{query}"
    raw = _fetch_url(url, headers={"Accept": "application/vnd.github+json"})
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [
            {"name": r["full_name"], "stars": r["stargazers_count"], "url": r["html_url"],
             "default_branch": r.get("default_branch", "main")}
            for r in data.get("items", [])
            if r.get("stargazers_count", 0) >= min_stars
        ]
    except (json.JSONDecodeError, KeyError):
        return []


def _fetch_repo_content(repos: list[dict]) -> list[str]:
    def _try_repo(repo: dict) -> str | None:
        for filename in (".cursorrules", "cursor-rules.md", ".cursor/rules/main.mdc"):
            url = (
                f"{get_github_raw_base_url()}/{repo['name']}"
                f"/{repo['default_branch']}/{filename}"
            )
            content = _fetch_url(url)
            if content:
                header = f"# Source: {repo['name']} ({repo['stars']} stars)\n\n"
                return header + content[:_CONTENT_SAMPLE_LIMIT]
        return None

    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(len(repos), _MAX_FETCH_WORKERS)) as executor:
        future_to_repo = {executor.submit(_try_repo, repo): repo for repo in repos}
        for future in as_completed(future_to_repo):
            repo = future_to_repo[future]
            result = future.result()
            if result:
                results[repo["name"]] = result

    return [results[repo["name"]] for repo in repos if repo["name"] in results]


class _FetchClient:
    """Thread-safe HTTP fetcher with circuit breaker (trips after repeated failures)."""

    _CIRCUIT_THRESHOLD = 5

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._failures = 0

    def fetch(self, url: str, headers: dict | None = None) -> str | None:
        """Fetch *url* and return body text, or None on failure."""
        with self._lock:
            if self._failures >= self._CIRCUIT_THRESHOLD:
                return None
        try:
            req = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT_S) as r:
                with self._lock:
                    self._failures = 0
                return r.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, OSError, ValueError):
            with self._lock:
                self._failures += 1
            return None


_fetch_client: _FetchClient | None = None


def _get_fetch_client() -> _FetchClient:
    """Return the module-level _FetchClient, creating it lazily on first use."""
    global _fetch_client
    if _fetch_client is None:
        _fetch_client = _FetchClient()
    return _fetch_client


def _fetch_url(url: str, headers: dict | None = None) -> str | None:
    return _get_fetch_client().fetch(url, headers)


def _build_practices_prompt(runtime: str, content_samples: list[str], out_path: Path) -> str:
    combined = "\n\n---\n\n".join(content_samples)
    existing = out_path.read_text() if out_path.exists() else "none"
    try:
        template = (_REFRESH_TEMPLATES_DIR / "practices.md").read_text()
    except (OSError, UnicodeDecodeError) as exc:
        raise FileNotFoundError(f"Cannot read practices template: {exc}") from exc
    return render_template(template, {
        "RUNTIME": runtime,
        "EXISTING": existing,
        "COMBINED": combined,
    })


def _build_analysis_prompt(runtime: str, linter_docs: str, out_path: Path) -> str:
    existing = out_path.read_text() if out_path.exists() else "none"
    try:
        template = (_REFRESH_TEMPLATES_DIR / "analysis.md").read_text()
    except (OSError, UnicodeDecodeError) as exc:
        raise FileNotFoundError(f"Cannot read analysis template: {exc}") from exc
    return render_template(template, {
        "RUNTIME": runtime,
        "RUNTIME_TITLE": runtime.title(),
        "EXISTING": existing[:_EXISTING_CONTENT_LIMIT] if existing != "none" else "none",
        "LINTER_DOCS": linter_docs[:_LINTER_DOCS_LIMIT],
    })


