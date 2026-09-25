"""The already-dismissed findings a findings router downweights against."""
from __future__ import annotations

from pathlib import Path

from quodeq.config.context_env import precedent_settings
from quodeq.context.precedent import load_precedent_corpus, load_precedent_fingerprints
from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.data.sqlite.findings_queries import (
    dismissed_source_stamp,
    read_dismissed_snippets_strict,
)
from quodeq.services.precedent_dismiss import precedent_match_hook


def precedent_signals(
    project_dir: Path | None, run_dir: Path | None, *, log: LogSink = NULL_LOG,
) -> dict[str, object]:
    """The ``CompiledContext`` precedent fields for *project_dir* and *run_dir*.

    Without a project there are no dismissals and no corpus; without a run
    directory there is no corpus. The strict reader raises on a failed open,
    so the per-run memo skips the run instead of remembering it as having no
    dismissals. The corpus reads its settings from this process's env.
    *log* receives the auto-dismiss hook's warnings.
    """
    if not project_dir:
        return {"precedent_fingerprints": set(), "precedent_corpus": None,
                "on_precedent_match": precedent_match_hook(None, log=log)}
    return {
        "precedent_fingerprints": load_precedent_fingerprints(
            project_dir, read_dismissed=read_dismissed_snippets_strict,
            source_stamp=dismissed_source_stamp,
        ),
        "precedent_corpus": (
            load_precedent_corpus(project_dir, run_dir, settings=precedent_settings()) if run_dir else None),
        "on_precedent_match": precedent_match_hook(project_dir, log=log),
    }
