"""Tests for the pure clickable-terminal-link helpers in quodeq.terminal.links.

No real filesystem, PATH, or subprocess; the /api/terminal/resolve + /open
routes live in test_terminal_links_routes.py.
"""
from __future__ import annotations

from quodeq.terminal.links import (
    Editor,
    PathOps,
    build_open_argv,
    child_cwd,
    detect_editor,
    resolve_path,
    safe_editor_path,
)


# POSIX-style path primitives injected into the pure helpers so these logic
# tests are deterministic on every OS (the host's os.path uses \ on Windows,
# which would break literal "/foo" assertions without exercising real logic).
def _pjoin(a, b):
    return a.rstrip("/") + "/" + b


def _ident(p):
    return p


def _pisabs(p):
    return p.startswith("/")


def _pcommonpath(paths):
    a, base = paths
    b = base.rstrip("/")
    return base if (a == base or a == b or a.startswith(b + "/")) else "/"


# --- resolve_path -----------------------------------------------------------

def _posix_ops(isfile) -> PathOps:
    return PathOps(isabs=_pisabs, isfile=isfile, join=_pjoin, normpath=_ident, expanduser=_ident)


def test_resolve_absolute_existing():
    abs_path, exists = resolve_path(
        "/proj/a.py", ["/base"], ops=_posix_ops(lambda p: p == "/proj/a.py"),
    )
    assert abs_path == "/proj/a.py"
    assert exists is True


def test_resolve_absolute_missing():
    abs_path, exists = resolve_path("/nope.py", ["/base"], ops=_posix_ops(lambda p: False))
    assert abs_path == "/nope.py"
    assert exists is False


def test_resolve_relative_picks_first_existing_base():
    # Exists only under the second base.
    real = "/second/rel.py"
    abs_path, exists = resolve_path(
        "rel.py", ["/first", "/second"], ops=_posix_ops(lambda p: p == real),
    )
    assert abs_path == real
    assert exists is True


def test_resolve_relative_none_exist_falls_back_to_first_base():
    abs_path, exists = resolve_path(
        "rel.py", ["/first", "/second"], ops=_posix_ops(lambda p: False),
    )
    assert abs_path == "/first/rel.py"
    assert exists is False


# --- safe_editor_path -------------------------------------------------------

def test_safe_editor_path_within_base_returns_realpath():
    got = safe_editor_path("/home/u/proj/a.py", ["/home/u"],
                           realpath=_ident, commonpath=_pcommonpath)
    assert got == "/home/u/proj/a.py"


def test_safe_editor_path_outside_bases_is_none():
    assert safe_editor_path("/etc/passwd", ["/home/u"],
                            realpath=_ident, commonpath=_pcommonpath) is None


def test_safe_editor_path_symlink_escape_rejected():
    # realpath resolves the link OUT of the base -> rejected (not just lexical).
    def _rp(p):
        return "/etc/shadow" if p == "/home/u/link" else p

    assert safe_editor_path("/home/u/link", ["/home/u"],
                            realpath=_rp, commonpath=_pcommonpath) is None


def test_safe_editor_path_normalizes_returned_value():
    # realpath collapses the `..`; the returned value is the normalized one.
    got = safe_editor_path(
        "/home/u/../u/proj/a.py", ["/home/u"],
        realpath=lambda p: "/home/u/proj/a.py" if ".." in p else p,
        commonpath=_pcommonpath,
    )
    assert got == "/home/u/proj/a.py"


def test_safe_editor_path_checks_multiple_bases():
    got = safe_editor_path("/second/a.py", ["/first", "/second"],
                           realpath=_ident, commonpath=_pcommonpath)
    assert got == "/second/a.py"


def test_safe_editor_path_null_byte_returns_none():
    # A NUL byte must never reach the editor launch. POSIX realpath raises
    # ValueError on it (previously an uncaught 500), while Windows realpath
    # returns it intact under the base; both must resolve to None. Uses the
    # real os.path.realpath so the platform behavior is exercised.
    assert safe_editor_path("/home/u/a\x00.py", ["/home/u"]) is None


# --- detect_editor ----------------------------------------------------------

def test_detect_editor_prefers_code_on_path():
    ed = detect_editor(which=lambda n: "/usr/bin/code" if n == "code" else None,
                       isfile=lambda p: False, platform="darwin")
    assert ed == Editor(name="code", path="/usr/bin/code", supports_line=True)


def test_detect_editor_finds_code_via_known_location_when_path_misses():
    # GUI-launched macOS app: `code` not on PATH, but the bundled CLI exists.
    bundled = "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"
    ed = detect_editor(which=lambda n: None, isfile=lambda p: p == bundled,
                       platform="darwin")
    assert ed.name == "code" and ed.path == bundled and ed.supports_line


def test_detect_editor_falls_back_to_cursor_then_open():
    ed = detect_editor(which=lambda n: "/opt/homebrew/bin/cursor" if n == "cursor" else None,
                       isfile=lambda p: False, platform="darwin")
    assert ed.name == "cursor"

    ed2 = detect_editor(which=lambda n: None, isfile=lambda p: False, platform="darwin")
    assert ed2.name == "open" and ed2.supports_line is False


def test_detect_editor_none_when_no_opener():
    ed = detect_editor(which=lambda n: None, isfile=lambda p: False, platform="linux")
    # No xdg-open either.
    assert ed is None


# --- build_open_argv --------------------------------------------------------

def test_build_argv_code_with_line_col():
    ed = Editor("code", "/usr/bin/code", True)
    assert build_open_argv(ed, "/a.py", 12, 4) == ["/usr/bin/code", "-g", "/a.py:12:4"]


def test_build_argv_code_line_only():
    ed = Editor("code", "/usr/bin/code", True)
    assert build_open_argv(ed, "/a.py", 12, None) == ["/usr/bin/code", "-g", "/a.py:12"]


def test_build_argv_code_no_line():
    ed = Editor("code", "/usr/bin/code", True)
    assert build_open_argv(ed, "/a.py", None, None) == ["/usr/bin/code", "-g", "/a.py"]


def test_build_argv_open_ignores_line():
    ed = Editor("open", "/usr/bin/open", False)
    assert build_open_argv(ed, "/a.py", 12, 4) == ["/usr/bin/open", "/a.py"]


def test_build_argv_startfile_sentinel_is_none():
    ed = Editor("startfile", "startfile", False)
    assert build_open_argv(ed, "/a.py", 1, 1) is None


# --- child_cwd --------------------------------------------------------------

def test_child_cwd_linux_readlink():
    got = child_cwd(123, platform="linux", readlink=lambda p: "/proc-cwd" if p == "/proc/123/cwd" else None)
    assert got == "/proc-cwd"


def test_child_cwd_darwin_parses_lsof():
    class _Proc:
        stdout = "p123\nfcwd\nn/Users/x/live\n"

    got = child_cwd(123, platform="darwin", run=lambda *a, **k: _Proc())
    assert got == "/Users/x/live"


def test_child_cwd_none_without_pid():
    assert child_cwd(None) is None


def test_child_cwd_swallows_errors():
    def _boom(*a, **k):
        raise OSError("nope")

    assert child_cwd(123, platform="linux", readlink=_boom) is None
