from __future__ import annotations

import sys

_OK   = "✓"
_ERR  = "✗"
_WARN = "!"
_STEP = "→"
_BEAT = "·"
_THIN = "─"
_BOLD = "━"
_WIDTH = 48


def log_step(message: str) -> None:
    """In-progress phase indicator (→ message)."""
    print(f"  {_STEP} {message}", flush=True)


def log_info(message: str) -> str:
    """Plain informational line, indented."""
    formatted = f"  {message}"
    print(formatted, flush=True)
    return formatted


def log_success(message: str) -> str:
    formatted = f"  {_OK} {message}"
    print(formatted, flush=True)
    return formatted


def log_warning(message: str) -> str:
    formatted = f"  {_WARN} {message}"
    print(formatted, file=sys.stderr, flush=True)
    return formatted


def log_error(message: str) -> str:
    formatted = f"  {_ERR} {message}"
    print(formatted, file=sys.stderr, flush=True)
    return formatted


def log_beat(message: str) -> None:
    """Heartbeat / still-running indicator (· message)."""
    print(f"  {_BEAT} {message}", flush=True)


def log_divider(label: str = "", width: int = _WIDTH) -> None:
    """Thin dimension section header: ─── [1/3] resilience ──────"""
    if label:
        inner = f" {label} "
        dashes = max(1, width - len(inner) - 3)
        print(f"\n  {_THIN * 3}{inner}{_THIN * dashes}", flush=True)
    else:
        print(f"\n  {_THIN * width}", flush=True)


def log_banner(lines: list[str], width: int = _WIDTH) -> None:
    """Bold border section (━ lines above and below)."""
    border = _BOLD * width
    print(f"\n{border}", flush=True)
    for line in lines:
        print(f"  {line}", flush=True)
    print(border, flush=True)


def fail_with_error(message: str) -> int:
    log_error(message)
    return 1
