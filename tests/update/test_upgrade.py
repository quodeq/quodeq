import io
import subprocess
from unittest.mock import patch

import pytest

from quodeq.update import upgrade

_ARGV = ["pipx", "upgrade", "quodeq"]


def _status(latest):
    return {"latest": latest, "download_url": None, "latest_url": None}


@pytest.fixture
def no_network():
    with patch("quodeq.update.upgrade.run_check"):
        yield


def _run(latest="99.0.0", argv=_ARGV, returncode=0, **kwargs):
    out = io.StringIO()
    calls = []

    def fake_run(cmd, check):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode)

    with patch("quodeq.update.upgrade.upgrade_argv", return_value=argv), \
         patch("quodeq.update.upgrade.get_status", return_value=_status(latest)):
        code = upgrade.run_upgrade(
            out=out, run=fake_run, which=kwargs.pop("which", lambda name: "/bin/" + name), **kwargs,
        )
    return code, out.getvalue(), calls


def test_runs_the_detected_command(no_network, argv_as_written) -> None:
    code, out, calls = _run()
    assert code == 0
    assert calls == [_ARGV]
    assert "Upgraded" in out


def test_dry_run_prints_without_running(no_network) -> None:
    code, out, calls = _run(dry_run=True)
    assert code == 0
    assert calls == []
    assert "Would run: pipx upgrade quodeq" in out


def test_up_to_date_runs_nothing(no_network) -> None:
    code, out, calls = _run(latest="0.0.1")
    assert code == 0
    assert calls == []
    assert "is the latest version" in out


def test_unknown_latest_still_upgrades(no_network, argv_as_written) -> None:
    code, _out, calls = _run(latest=None)
    assert code == 0
    assert calls == [_ARGV]


def test_failed_upgrade_returns_its_exit_code(no_network) -> None:
    code, out, _calls = _run(returncode=3)
    assert code == 3
    assert "failed" in out


def test_missing_tool_prints_the_command(no_network) -> None:
    code, out, calls = _run(which=lambda name: None)
    assert code == 1
    assert calls == []
    assert "pipx upgrade quodeq" in out


def test_frozen_app_points_at_the_download(no_network) -> None:
    code, out, calls = _run(argv=None)
    assert code == 1
    assert calls == []
    assert "releases/latest" in out
