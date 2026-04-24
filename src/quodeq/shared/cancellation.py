"""Process-wide cancellation signal for long-running evaluations.

One evaluation runs per Python process. The SIGTERM/SIGINT handler in
run_lifecycle calls ``request_cancel()``; worker threads deep in the
analysis pipeline poll ``is_cancelled()`` (or wait on ``get_event()``) so
they can terminate their child AI CLI subprocesses promptly instead of
blocking ``ThreadPoolExecutor.shutdown`` on long Ollama inference calls.
"""
from __future__ import annotations

import threading

_event = threading.Event()


def get_event() -> threading.Event:
    return _event


def is_cancelled() -> bool:
    return _event.is_set()


def request_cancel() -> None:
    _event.set()


def reset() -> None:
    _event.clear()
