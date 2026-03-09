from __future__ import annotations

import difflib
import json
import urllib.request
import urllib.parse
from pathlib import Path

from quodeq.config import generators

# Per-runtime linter documentation sources
_LINTER_SOURCES: dict[str, str] = {
    "typescript": (
        "https://raw.githubusercontent.com/typescript-eslint/typescript-eslint"
        "/main/packages/eslint-plugin/README.md"
    ),
    "kotlin": (
        "https://raw.githubusercontent.com/detekt/detekt/main/website/docs/rules/complexity.md"
    ),
    "python": (
        "https://raw.githubusercontent.com/astral-sh/ruff/main/docs/rules.md"
    ),
    "bash": (
        "https://raw.githubusercontent.com/koalaman/shellcheck/master/README.md"
    ),
    "java": (
        "https://raw.githubusercontent.com/pmd/pmd/main/docs/pages/pmd/rules/java/bestpractices.md"
    ),
    "mobile_ios": (
        "https://raw.githubusercontent.com/realm/SwiftLint/main/README.md"
    ),
}

_GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"


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
        print(f"No cursor-rules repos found for runtime={runtime!r} with min_stars={min_stars}")
        return 1

    content_samples = _fetch_repo_content(repos[:3])
    if not content_samples:
        print("Could not fetch content from any repo")
        return 1

    prompt = _build_practices_prompt(runtime, content_samples, out_path)
    stdout, err = generators.run_ai_cli(prompt)
    if err:
        print(f"LLM error: {err}")
        return 1

    try:
        payload = json.loads(stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        print(f"LLM returned invalid JSON: {exc}")
        return 1

    new_content = json.dumps(payload, indent=2)
    if dry_run:
        count = len(payload.get("practices", []))
        print(f"[dry-run] Would write {count} practices to {out_path}")
        _show_diff(out_path, new_content)
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(new_content)
    print(f"Written {len(payload.get('practices', []))} practices to {out_path}")
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

    source_url = _LINTER_SOURCES.get(runtime)
    if not source_url:
        print(f"No linter source configured for runtime={runtime!r}")
        print(f"Supported runtimes: {', '.join(sorted(_LINTER_SOURCES))}")
        return 1

    linter_docs = _fetch_url(source_url)
    if not linter_docs:
        print(f"Could not fetch linter docs from {source_url}")
        return 1

    prompt = _build_analysis_prompt(runtime, linter_docs, out_path)
    stdout, err = generators.run_ai_cli(prompt)
    if err:
        print(f"LLM error: {err}")
        return 1

    if dry_run:
        print(f"[dry-run] Would write analysis.md to {out_path}")
        _show_diff(out_path, stdout)
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(stdout)
    print(f"Written analysis.md to {out_path}")
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
    url = f"{_GITHUB_SEARCH_URL}?{query}"
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
    samples = []
    for repo in repos:
        for filename in (".cursorrules", "cursor-rules.md", ".cursor/rules/main.mdc"):
            url = (
                f"https://raw.githubusercontent.com/{repo['name']}"
                f"/{repo['default_branch']}/{filename}"
            )
            content = _fetch_url(url)
            if content:
                header = f"# Source: {repo['name']} ({repo['stars']} stars)\n\n"
                samples.append(header + content[:4000])
                break
    return samples


def _fetch_url(url: str, headers: dict | None = None) -> str | None:
    try:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def _build_practices_prompt(runtime: str, content_samples: list[str], out_path: Path) -> str:
    combined = "\n\n---\n\n".join(content_samples)
    existing = out_path.read_text() if out_path.exists() else "none"
    return f"""You are curating engineering practices for the {runtime} runtime.

Below are cursor-rules files from highly-starred GitHub repositories. Extract the most
impactful violations — code patterns that real teams actually get wrong.

For each violation produce a JSON object with these exact fields:
- id: string like "ts-NNN"
- title: short imperative title
- cwe: integer CWE ID (use the closest match, e.g. 95 for eval, 798 for secrets)
- dimension: one of maintainability | reliability | security | performance
- severity: one of low | medium | high | critical
- bad: minimal bad code snippet (1-3 lines)
- good: corrected snippet (1-3 lines)
- explanation: 1-2 sentences on why it matters

Return ONLY valid JSON in this shape (no markdown fences):
{{
  "runtime": "{runtime}",
  "version": "1.0.0",
  "source": "curated from GitHub cursor-rules repos",
  "practices": [ ... ]
}}

Existing practices (do not duplicate):
{existing}

--- SOURCE MATERIAL ---
{combined}
"""


def _build_analysis_prompt(runtime: str, linter_docs: str, out_path: Path) -> str:
    existing = out_path.read_text() if out_path.exists() else "none"
    return f"""You are writing an analysis guidance document for the {runtime} runtime.

The document teaches a code analysis LLM:
1. Where to look in a {runtime} codebase (which files, which patterns)
2. What to ask the LLM judge when reviewing findings
3. Common false positives to ignore

Use the linter documentation below as your source of truth for rule names and severity.

Output ONLY valid markdown (no JSON). Use these sections:
# {runtime.title()} Codebase Analysis Guidance
## Where to look first
### Security hotspots
### Maintainability signals
### Reliability signals
### Performance signals
## What to ask the LLM
## Common false positives

Existing document (update in place, preserve what's accurate):
{existing[:2000] if existing != "none" else "none"}

--- LINTER DOCS ---
{linter_docs[:6000]}
"""


def _show_diff(path: Path, new_content: str) -> None:
    old_lines = path.read_text().splitlines(keepends=True) if path.exists() else []
    new_lines = new_content.splitlines(keepends=True)
    diff = list(difflib.unified_diff(old_lines, new_lines, fromfile=str(path), tofile="<new>"))
    if diff:
        print("".join(diff))
    else:
        print(f"[no changes] {path}")
