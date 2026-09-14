"""A malformed rate-limit env var must fall back, not crash the module at import time.

Mirrors quodeq.menubar.app's established try/except-with-fallback for the
same class of env var (QUODEQ_POLL_INTERVAL).
"""
from __future__ import annotations

import importlib

from quodeq.api import app as app_module


def test_malformed_rate_limit_window_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("QUODEQ_RATE_LIMIT_WINDOW", "not-a-number")
    monkeypatch.delenv("QUODEQ_RATE_LIMIT_MAX", raising=False)
    try:
        reloaded = importlib.reload(app_module)
        assert reloaded._EVALUATION_RATE_LIMIT_WINDOW == 300
        assert reloaded._EVALUATION_RATE_LIMIT_MAX == 10
    finally:
        importlib.reload(app_module)


def test_malformed_rate_limit_max_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("QUODEQ_RATE_LIMIT_MAX", "")
    monkeypatch.delenv("QUODEQ_RATE_LIMIT_WINDOW", raising=False)
    try:
        reloaded = importlib.reload(app_module)
        assert reloaded._EVALUATION_RATE_LIMIT_MAX == 10
        assert reloaded._EVALUATION_RATE_LIMIT_WINDOW == 300
    finally:
        importlib.reload(app_module)


def test_valid_rate_limit_env_vars_parse_unchanged(monkeypatch):
    monkeypatch.setenv("QUODEQ_RATE_LIMIT_WINDOW", "60")
    monkeypatch.setenv("QUODEQ_RATE_LIMIT_MAX", "5")
    try:
        reloaded = importlib.reload(app_module)
        assert reloaded._EVALUATION_RATE_LIMIT_WINDOW == 60
        assert reloaded._EVALUATION_RATE_LIMIT_MAX == 5
    finally:
        importlib.reload(app_module)
