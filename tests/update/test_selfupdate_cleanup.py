"""Self-update cleanup-path test: a second subprocess failure during
teardown must not shadow the primary error or skip cleanup. Reuses
test_selfupdate's engine-test helpers.
"""
from __future__ import annotations

import plistlib
import subprocess
from pathlib import Path
from unittest.mock import patch

from quodeq.update import selfupdate

from tests.update.test_selfupdate import (
    DMG_URL,
    _FakeCommands,
    _reset_state,  # noqa: F401 -- pytest autouse fixture, reused here
    _run_engine,
)


class _AlwaysTimeoutOnDetach(_FakeCommands):
    """`hdiutil detach` always times out: the primary detach (in the try
    block) and the finally-block retry both fail the same way."""

    def __call__(self, argv, **kwargs):
        if Path(argv[0]).name == "hdiutil" and argv[1] == "detach":
            raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs.get("timeout", 60))
        return super().__call__(argv, **kwargs)


def test_double_detach_timeout_still_cleans_up_and_reports_the_first_error(tmp_path: Path) -> None:
    """If the primary hdiutil detach times out AND the finally-block retry
    also times out, the retry's failure is logged and swallowed: cleanup
    still runs and the original timeout is the error that stands, instead of
    a second TimeoutExpired escaping to run_isolated's generic message."""
    fake = _AlwaysTimeoutOnDetach(mount_root=tmp_path / "mnt-root")
    with patch("quodeq.update.selfupdate._mountpoint_for_tests", tmp_path / "mnt-root"):
        install_app, fake, popen, exits = _run_engine(tmp_path, fake)

    status = selfupdate.describe(DMG_URL)
    assert status["phase"] == "error"
    assert "timed out" in status["error"]
    version = plistlib.loads((install_app / "Contents" / "Info.plist").read_bytes())
    assert version["CFBundleShortVersionString"] == "1.10.1"
    assert popen.call_count == 0 and exits == []
