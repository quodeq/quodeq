from __future__ import annotations

import sys


def log_info(message: str) -> str:
    formatted = f"[INFO] {message}"
    print(formatted, flush=True)
    return formatted


def log_error(message: str) -> str:
    formatted = f"[ERROR] {message}"
    print(formatted, file=sys.stderr)
    return formatted


def log_warning(message: str) -> str:
    formatted = f"[WARNING] {message}"
    print(formatted, file=sys.stderr)
    return formatted


def log_success(message: str) -> str:
    formatted = f"[SUCCESS] {message}"
    print(formatted, flush=True)
    return formatted


def fail_with_error(message: str) -> int:
    log_error(message)
    return 1
