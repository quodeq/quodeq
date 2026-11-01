"""OS sandbox launcher prefixes for agent CLIs Quodeq does not trust to sandbox themselves.

Shared by assistant turns and analysis runs. Writes are denied everywhere
except the given paths and system temp. When *readable_home_dirs* is given,
file contents under the user's home are unreadable too, except under those
dirs, so a prompt-injected agent cannot read ~/.ssh, ~/.aws or another
repo's .env. Metadata stays readable so path resolution keeps working.
With *block_loopback* (macOS only), the agent cannot reach services on this
machine, such as Quodeq's own API, except a local proxy's port.
"""
from __future__ import annotations

import platform
import shutil
import sys
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from quodeq.shared.constants import SYSTEM_DARWIN, SYSTEM_LINUX


def _under_home(path: Path) -> bool:
    return path.resolve().is_relative_to(Path.home().resolve())


def _binary_root(binary: str) -> Path | None:
    """The install prefix of *binary* (``<prefix>/bin/<binary>``), when under home."""
    found = shutil.which(binary)
    if not found:
        return None
    root = Path(found).resolve().parent.parent
    return root if _under_home(root) else None


def runtime_readable_dirs(*binaries: str) -> list[Path]:
    """What a sandboxed CLI and the Python MCP server it spawns must read to
    start: this interpreter, the quodeq package, and each binary's install
    prefix (plus node's, for node-based CLIs) when they live under home."""
    dirs = [Path(sys.prefix), Path(sys.base_prefix), Path(__file__).resolve().parents[2]]
    for binary in (*binaries, "node"):
        root = _binary_root(binary)
        if root is not None:
            dirs.append(root)
    return dirs


_BIND = "--bind"
_RO_BIND = "--ro-bind"
_PROXY_ENV_KEYS = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy",
                   "ALL_PROXY", "all_proxy")
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def loopback_proxy_ports(env: Mapping[str, str]) -> list[int]:
    """Ports of the proxies in *env* that run on this machine: the CLI must
    still reach them when loopback is blocked."""
    ports: set[int] = set()
    for key in _PROXY_ENV_KEYS:
        raw = env.get(key)
        if not raw:
            continue
        try:
            parts = urlsplit(raw if "://" in raw else f"http://{raw}")
            if parts.hostname in _LOOPBACK_HOSTS and parts.port:
                ports.add(parts.port)
        except ValueError:
            continue
    return sorted(ports)


def _sb_quote(path: str) -> str:
    return '"' + path.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _seatbelt_profile(*, writable_dirs: list[str], writable_files: list[str],
                      readable_home_dirs: list[str] | None = None,
                      readonly_dirs: list[str] | None = None,
                      block_loopback: bool = False,
                      loopback_allow_ports: Iterable[int] = ()) -> str:
    """macOS Seatbelt (SBPL): allow reads/exec, deny all file writes except the
    given paths and system temp. Later rules win, so each allow overrides the
    deny before it."""
    lines = ["(version 1)", "(allow default)"]
    if readable_home_dirs is not None:
        lines.append(f"(deny file-read-data (subpath {_sb_quote(str(Path.home()))}))")
        filters = [f"  (subpath {_sb_quote(d)})" for d in [*readable_home_dirs, *writable_dirs]]
        filters += [f"  (literal {_sb_quote(f)})" for f in writable_files]
        # A filterless allow would match everything and undo the deny above.
        if filters:
            lines += ["(allow file-read-data", *filters, ")"]
    lines += ["(deny file-write*)", "(allow file-write*"]
    for d in ["/private/tmp", "/private/var/folders", *writable_dirs]:
        lines.append(f"  (subpath {_sb_quote(d)})")
    for f in writable_files:
        lines.append(f"  (literal {_sb_quote(f)})")
    lines.append('  (literal "/dev/null") (literal "/dev/stdout") (literal "/dev/stderr")'
                 ' (literal "/dev/dtracehelper") (subpath "/dev/fd"))')
    if readonly_dirs:
        # After the temp allow, so a repo under /tmp stays read-only too; then
        # any writable dir nested inside it is allowed again.
        lines += [f"(deny file-write* (subpath {_sb_quote(d)}))" for d in readonly_dirs]
        nested = [d for d in writable_dirs
                  if any(Path(d).is_relative_to(r) for r in readonly_dirs)]
        lines += [f"(allow file-write* (subpath {_sb_quote(d)}))" for d in nested]
    if block_loopback:
        lines.append('(deny network-outbound (remote ip "localhost:*"))')
        lines += [f'(allow network-outbound (remote ip "localhost:{port}"))'
                  for port in loopback_allow_ports]
    return "\n".join(lines) + "\n"


def _writable_paths(writable_dirs: list[str], writable_files: list[str]) -> list[str]:
    """Every path the sandbox must allow writes under.

    The writable dirs themselves, plus the parent of each writable file -- a
    sandbox grants a directory, not a single file.
    """
    return [*writable_dirs, *(str(Path(f).parent) for f in writable_files)]


def _bwrap_prefix(writable_dirs: list[str], writable_files: list[str],
                  readable_home_dirs: list[str] | None = None,
                  readonly_dirs: list[str] | None = None) -> list[str]:
    argv = ["bwrap", _RO_BIND, "/", "/", "--dev", "/dev", "--proc", "/proc",
            "--tmpfs", "/tmp", "--share-net", "--die-with-parent", "--unshare-pid"]
    seen: set[str] = set()
    if readable_home_dirs is not None:
        # An empty home, then each readable dir mounted back read-only.
        argv += ["--tmpfs", str(Path.home())]
        for d in readable_home_dirs:
            if d and d not in seen and Path(d).exists():
                seen.add(d)
                argv += [_RO_BIND, d, d]
    for d in _writable_paths(writable_dirs, writable_files):
        if d and d not in seen:
            seen.add(d)
            argv += [_BIND, d, d]
    # Mounted last: a writable parent bound above (the repo of a remote
    # project lives under Quodeq's state) would otherwise cover the repo's
    # read-only bind. Writable dirs nested inside go back on top.
    for r in readonly_dirs or []:
        if Path(r).exists():
            argv += [_RO_BIND, r, r]
            argv += [arg for d in writable_dirs if d != r and Path(d).is_relative_to(r)
                     for arg in (_BIND, d, d)]
    return argv


def external_sandbox_prefix(*, writable_dirs: list[str], writable_files: list[str],
                            readable_home_dirs: list[str] | None = None,
                            readonly_dirs: list[str] | None = None,
                            block_loopback: bool = False,
                            loopback_allow_ports: Iterable[int] = (),
                            ) -> tuple[list[str], Callable[[], None]]:
    """Return (argv_prefix, cleanup) that wraps a command in an OS sandbox which
    allows network but blocks file writes outside the given paths, and, with
    *readable_home_dirs*, file reads under home outside them. *readonly_dirs*
    stay unwritable even under system temp and under a writable parent.
    *block_loopback* denies connections to this machine except
    *loopback_allow_ports*; bwrap cannot filter by address, so on Linux it
    has no effect.

    Fails safe: raises if no sandbox mechanism is available on this platform, so
    an agent whose own sandbox is bypassed never runs unsandboxed.
    """
    system = platform.system()
    if system == SYSTEM_DARWIN:
        profile = _seatbelt_profile(writable_dirs=writable_dirs, writable_files=writable_files,
                                    readable_home_dirs=readable_home_dirs,
                                    readonly_dirs=readonly_dirs,
                                    block_loopback=block_loopback,
                                    loopback_allow_ports=loopback_allow_ports)
        tmp = tempfile.NamedTemporaryFile("w", suffix=".sb", delete=False)
        tmp.write(profile)
        tmp.close()

        def _cleanup() -> None:
            Path(tmp.name).unlink(missing_ok=True)
        return ["sandbox-exec", "-f", tmp.name], _cleanup
    if system == SYSTEM_LINUX:
        if shutil.which("bwrap"):
            return (_bwrap_prefix(writable_dirs, writable_files, readable_home_dirs, readonly_dirs),
                    lambda: None)
        if shutil.which("firejail") and readable_home_dirs is None:
            # firejail read-only whole fs, then allow-list the writable dirs
            argv = ["firejail", "--quiet", "--read-only=/"]
            for d in _writable_paths(writable_dirs, writable_files):
                argv.append(f"--read-write={d}")
            return argv, lambda: None
        raise RuntimeError(
            "This provider must run in an OS sandbox, which needs bubblewrap "
            "(or firejail for assistant turns); install it or pick another provider.")
    raise RuntimeError(
        f"OS sandboxing is unsupported on {system}; pick Claude or an API provider.")
