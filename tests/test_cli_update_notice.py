import io
from unittest.mock import patch

from quodeq import cli


class _TTY(io.StringIO):
    def isatty(self) -> bool:  # pretend we're an interactive terminal
        return True


def test_notice_prints_when_update_available() -> None:
    stream = _TTY()
    status = {"update_available": True, "current": "1.4.0", "latest": "1.5.0",
              "action_command": "pipx upgrade quodeq", "is_security": False, "disclosed": True}
    with patch("quodeq.cli.get_status", return_value=status), \
         patch("quodeq.cli.check_async"):
        cli.maybe_emit_cli_notice(stream=stream, env={})
    out = stream.getvalue()
    assert "1.5.0" in out and "pipx upgrade quodeq" in out


def test_no_notice_when_not_a_tty() -> None:
    stream = io.StringIO()  # isatty() -> False
    status = {"update_available": True, "current": "1.4.0", "latest": "1.5.0",
              "action_command": "x", "is_security": False, "disclosed": True}
    with patch("quodeq.cli.get_status", return_value=status), patch("quodeq.cli.check_async"):
        cli.maybe_emit_cli_notice(stream=stream, env={})
    assert stream.getvalue() == ""


def test_skipped_when_opted_out() -> None:
    stream = _TTY()
    status = {"update_available": True, "current": "1.4.0", "latest": "1.5.0",
              "action_command": "x", "is_security": False, "disclosed": True}
    with patch("quodeq.cli.get_status", return_value=status), patch("quodeq.cli.check_async"):
        cli.maybe_emit_cli_notice(stream=stream, env={"QUODEQ_NO_UPDATE_NOTIFIER": "1"})
    assert stream.getvalue() == ""


def test_disclosure_prints_once_then_marks() -> None:
    stream = _TTY()
    status = {"update_available": False, "current": "1.4.0", "latest": None,
              "action_command": "x", "is_security": False, "disclosed": False}
    with patch("quodeq.cli.get_status", return_value=status), \
         patch("quodeq.cli.check_async"), \
         patch("quodeq.cli.set_settings") as setn:
        cli.maybe_emit_cli_notice(stream=stream, env={})
    assert "checks" in stream.getvalue().lower()
    setn.assert_called_once_with(disclosed=True)
