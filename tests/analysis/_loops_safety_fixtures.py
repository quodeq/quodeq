"""Shared helpers for tests/analysis/test_loops_safety_*.py siblings.

Split out of test_loops_safety.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

from quodeq.analysis._types import _AnalysisContext


def _ctx(total: int) -> _AnalysisContext:
    """Minimal _AnalysisContext — only `total` is read by the loops."""
    return _AnalysisContext(
        dimensions_data=None,
        date_str="",
        template="",
        subagent_template="",
        total=total,
    )


def _config() -> MagicMock:
    """Minimal RunConfig stub for the few fields the loops dereference.

    ``skip_scoring=True`` makes ``check_zero_findings`` short-circuit so the
    safety tests can use a stub Evidence without wiring real principle data.
    """
    cfg = MagicMock()
    cfg.source_file_count = 100
    cfg.options.incremental_file_filter = None
    cfg.options.skip_scoring = True
    # Default: no run-level deadline (would otherwise be a MagicMock and
    # break the numeric comparison in the loop's deadline guard).
    cfg.options.deadline_at = None
    return cfg


@dataclass
class _FakeEvidence:
    files_read: int = 5
    # check_zero_findings (called after the loop) iterates principles —
    # an empty dict satisfies it without any findings logic.
    principles: dict = None  # type: ignore[assignment]
    # The DONE write site forwards Evidence.exit_reason into dimensions.json;
    # default None matches the real Evidence model so safe-write skips the field.
    exit_reason: str | None = None

    def __post_init__(self) -> None:
        if self.principles is None:
            object.__setattr__(self, "principles", {})


def _runner_from(fn):
    """Wrap a process-fn callable (`(cfg, dim, idx, ctx) -> Evidence`) into a
    DimensionRunner-shaped mock so it can be passed as ``runner=``.

    The new signature includes a keyword-only ``emit_log`` that the loops
    pass; tests don't care about it, so we accept and ignore it.
    """
    def _adapter(cfg, dim, idx, ctx, *, emit_log=True):
        return fn(cfg, dim, idx, ctx)

    runner = MagicMock()
    runner.run.side_effect = _adapter
    return runner
