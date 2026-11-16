"""Code enrichment: reads source files and fills snippet/context on findings.

Extracted from FindingsRouter to keep module sizes small.

Every text field that leaves here is secret-masked: the snippet and context
end up in evaluation.db, evidence JSONL, reports, shared publish and SARIF,
and a credential in the source must reach none of them.

A credential file (``core.secret_files``) is never read here at all. The
model names the file a finding is about, and text planted in a repository can
make it name ``.env``; such a finding keeps its file, line and reason and
gets a placeholder for its code.
"""
from __future__ import annotations

from pathlib import Path, PureWindowsPath
from typing import Callable

from quodeq.core.secret_files import secret_file_kind
from quodeq.core.secret_scan import placeholder, redact

CONTEXT_LINES = 5
_MAX_SNIPPET_LINES = 40  # cap for scope-level snippets
SECRET_FILE_SNIPPET = placeholder("secret_file")  # stands in for the code of a credential file


def _extract_window(source: str, line: int, end_line: int, context: int) -> list[str]:
    """Extract a bounded window of lines from *source* around [line, end_line].

    Only splits and retains the lines within the window instead of keeping
    the full splitlines() list alive.  *line* and *end_line* are 1-indexed.
    """
    win_start = max(0, line - 1 - context)  # 0-indexed
    win_end = end_line + context  # exclusive
    # Split lazily by iterating; stop once we've passed the window.
    result: list[str] = []
    idx = 0
    start = 0
    while start <= len(source):
        end = source.find("\n", start)
        if end == -1:
            end = len(source)
            if idx >= win_start:
                result.append(source[start:end])
            break
        if idx >= win_start:
            result.append(source[start:end])
        idx += 1
        start = end + 1
        if idx >= win_end:
            break
    return result


def _enrich_line_level(
    finding: dict, source: str, line: int,
) -> None:
    """Fill snippet and context for a line-level finding."""
    end_line = finding.get("end_line") or line
    if end_line < line:
        line, end_line = end_line, line

    window = _extract_window(source, line, end_line, CONTEXT_LINES)
    if not window:
        finding.setdefault("snippet", "")
        finding.setdefault("context", "")
        return

    win_start_1 = max(1, line - CONTEXT_LINES)  # 1-indexed start of window
    snippet_parts: list[str] = []
    context_parts: list[str] = []
    for i, text in enumerate(window):
        lno = win_start_1 + i
        if line <= lno <= end_line:
            snippet_parts.append(text)
            context_parts.append(f">>> {text}")
        else:
            context_parts.append(text)
    finding["snippet"] = "\n".join(snippet_parts)
    finding["context"] = "\n".join(context_parts)


# Fields a model or the source can put a credential into.
_MASKED_FIELDS = ("snippet", "context", "reason", "w", "title")


def mask_secrets(finding: dict) -> None:
    """Replace any secret in *finding*'s text fields with its typed placeholder."""
    for key in _MASKED_FIELDS:
        value = finding.get(key)
        if isinstance(value, str) and value:
            finding[key] = redact(value)


def enrich_code(
    finding: dict,
    work_dir: Path | None,
    read_file: Callable[[Path], str],
) -> None:
    """Fill snippet and context by reading the source file from *work_dir*,
    then mask any secret in them (and in the model's own text)."""
    _fill_code(finding, work_dir, read_file)
    mask_secrets(finding)


def _is_secret_file(path: str) -> bool:
    """True when *path* (either separator) names a credential file."""
    return secret_file_kind(PureWindowsPath(path).name) is not None


def _withhold_code(finding: dict) -> None:
    finding["snippet"] = SECRET_FILE_SNIPPET
    finding["context"] = ""


def _fill_code(
    finding: dict,
    work_dir: Path | None,
    read_file: Callable[[Path], str],
) -> None:
    file_path = finding.get("file")
    if not file_path:
        return
    if _is_secret_file(str(file_path)):  # whatever the model quoted from it goes too
        _withhold_code(finding)
        return
    if work_dir is None:
        return
    try:
        full_path = work_dir / file_path
        resolved = full_path.resolve()
        # Path containment check: prevent traversal outside the work directory.
        if not resolved.is_relative_to(work_dir.resolve()):
            finding.setdefault("snippet", "")
            finding.setdefault("context", "")
            return
        if _is_secret_file(resolved.name):  # a link to one under another name
            _withhold_code(finding)
            return
        # Redact the whole file before windowing: a window that starts inside
        # a PEM body has no header left to recognise it by.
        source = redact(read_file(full_path))
    except (OSError, UnicodeDecodeError):
        finding.setdefault("snippet", "")
        finding.setdefault("context", "")
        return

    line = finding.get("line", 0)
    scope = finding.get("scope")

    # Scope-level or line=0: store capped snippet for expand-on-click
    if scope or not line:
        # Cap at _MAX_SNIPPET_LINES to avoid storing huge files in memory
        lines = source.split("\n", _MAX_SNIPPET_LINES + 1)
        if len(lines) > _MAX_SNIPPET_LINES:
            lines = lines[:_MAX_SNIPPET_LINES]
        finding["snippet"] = "\n".join(lines)
        finding["scope"] = scope or "file"
        finding["context"] = None
        return

    _enrich_line_level(finding, source, line)
