"""The Windows lock branch, driven through a fake msvcrt on any platform."""
from __future__ import annotations

import sys
import types

import pytest

from quodeq.core.constants import PLATFORM_WIN32
from quodeq.core.utils import file_lock


def _windows_lock(monkeypatch, failures: int):
    """A win32 ``_lock`` whose fake msvcrt refuses the first *failures* attempts."""
    calls: list[tuple[int, int, int]] = []
    fake = types.SimpleNamespace(LK_NBLCK=2, LK_UNLCK=0)

    def locking(fd: int, mode: int, nbytes: int) -> None:
        calls.append((fd, mode, nbytes))
        if len(calls) <= failures:
            raise OSError("locked")

    fake.locking = locking
    monkeypatch.setitem(sys.modules, "msvcrt", fake)
    monkeypatch.setattr(sys, "platform", PLATFORM_WIN32)
    lock, _unlock = file_lock._make_lock_ops()
    return lock, calls


def test_windows_lock_retries_until_the_lock_is_free(monkeypatch):
    lock, calls = _windows_lock(monkeypatch, failures=2)
    lock(7, 5.0)
    assert calls == [(7, 2, 1)] * 3


def test_windows_lock_reraises_the_os_error_after_the_budget(monkeypatch):
    lock, calls = _windows_lock(monkeypatch, failures=10**6)
    with pytest.raises(OSError, match="locked") as info:
        lock(7, 0.1)
    assert type(info.value) is OSError
    assert len(calls) >= 2
