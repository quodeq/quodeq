"""Self-update engine for the packaged macOS dashboard app.

Downloads the new release DMG, verifies it (notarization via spctl, signature
and pinned Team ID via codesign, version via Info.plist), stages a copy next to
the installed bundle, swaps it in with atomic renames, and relaunches.

Dormant until EXPECTED_TEAM_ID is set: describe() reports unsupported and the
UI keeps the plain download link. Only ever replaces the .app bundle; never
touches ~/.quodeq (shared with wheel installs and QuodeqBar).
"""

from __future__ import annotations

import logging
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlparse

import httpx

_logger = logging.getLogger(__name__)

# Apple Developer Team ID that release DMGs are signed with. Filled in once
# the Apple Developer enrollment completes; empty means self-update stays
# dormant and the update banner falls back to the manual download link.
EXPECTED_TEAM_ID: str = ""

# The only asset the dashboard app may replace itself with.
_ASSET_PREFIX = "Quodeq-"
_ASSET_SUFFIX = "-macOS.dmg"

_ACTIVE_PHASES = frozenset({"downloading", "verifying", "installing", "relaunching"})

_lock = threading.Lock()
_progress: dict = {"phase": "idle", "percent": 0, "error": None}
_thread: threading.Thread | None = None
_shutdown_callback = None

# Test seam: when set, used as the hdiutil mountpoint instead of a temp dir.
_mountpoint_for_tests: Path | None = None


class UpdateError(Exception):
    """A self-update failure with a message safe to show in the UI."""


def set_shutdown_callback(callback) -> None:
    """Install the app's graceful-quit function, used after a successful swap."""
    global _shutdown_callback
    _shutdown_callback = callback


def _set(**fields) -> None:
    with _lock:
        _progress.update(fields)


def _snapshot() -> dict:
    with _lock:
        return dict(_progress)


def bundle_path(executable: str | None = None) -> Path | None:
    """The enclosing .app bundle of *executable* (default: this process)."""
    exe = Path(executable or sys.executable)
    for parent in exe.parents:
        if parent.name.endswith(".app"):
            return parent
    return None


def _is_translocated(bundle: Path) -> bool:
    """Running from the mounted DMG or an App Translocation (read-only) path."""
    # Normalize separators so the check also behaves under Windows test runs.
    path = str(bundle).replace("\\", "/")
    return path.startswith("/Volumes/") or "/AppTranslocation/" in path


def _asset_matches(download_url: str | None) -> bool:
    if not download_url:
        return False
    name = Path(urlparse(download_url).path).name
    return name.startswith(_ASSET_PREFIX) and name.endswith(_ASSET_SUFFIX)


def describe(
    download_url: str | None,
    *,
    frozen: bool | None = None,
    platform: str | None = None,
    executable: str | None = None,
    team_id: str | None = None,
) -> dict:
    """Whether self-update is possible here, plus current progress."""
    reason = None
    is_frozen = frozen if frozen is not None else bool(getattr(sys, "frozen", False))
    plat = platform if platform is not None else sys.platform
    team = team_id if team_id is not None else EXPECTED_TEAM_ID
    bundle = bundle_path(executable)
    if not is_frozen:
        reason = "not_frozen"
    elif plat != "darwin":
        reason = "not_macos"
    elif not team:
        reason = "no_team_id"
    elif bundle is None:
        reason = "no_bundle"
    elif _is_translocated(bundle):
        reason = "translocated"
    elif not os.access(bundle.parent, os.W_OK):
        reason = "not_writable"
    elif not _asset_matches(download_url):
        reason = "no_asset"
    return {"supported": reason is None, "reason": reason, **_snapshot()}


def start(
    download_url: str,
    target_version: str,
    *,
    install_app: Path | None = None,
    team_id: str | None = None,
) -> bool:
    """Kick off the update in a daemon thread. False if one is already running."""
    global _thread
    app = install_app if install_app is not None else bundle_path()
    team = team_id if team_id is not None else EXPECTED_TEAM_ID
    if app is None or not team:
        return False
    with _lock:
        if _progress["phase"] in _ACTIVE_PHASES:
            return False
        _progress.update(phase="downloading", percent=0, error=None)
    _thread = threading.Thread(
        target=_run_update, args=(download_url, target_version, app, team), daemon=True
    )
    _thread.start()
    return True


def _check(argv: list[str], message: str) -> None:
    result = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        _logger.warning("self-update command failed (%s): %s", argv[0], result.stderr)
        raise UpdateError(message)


def _download_file(url: str, target: Path, progress) -> None:
    with httpx.stream(
        "GET", url, follow_redirects=True, timeout=httpx.Timeout(10.0, read=60.0)
    ) as response:
        response.raise_for_status()
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        with open(target, "wb") as out:
            for chunk in response.iter_bytes():
                out.write(chunk)
                done += len(chunk)
                if total:
                    progress(min(99, done * 100 // total))


def _request_app_exit() -> None:
    callback = _shutdown_callback
    if callback is not None:
        try:
            callback()
            return
        except Exception:
            _logger.debug("shutdown callback failed", exc_info=True)
    # Give the HTTP response that reported "relaunching" time to flush.
    threading.Timer(0.5, lambda: os._exit(0)).start()


def _verify_mounted_app(mnt: Path, app_name: str, team: str, target_version: str) -> Path:
    """Locate and verify the new bundle on the mounted DMG; returns its path."""
    app_src = Path(mnt) / app_name
    if not app_src.exists():
        raise UpdateError("The downloaded update does not contain the app")
    _check(
        ["codesign", "--verify", "--strict", "--deep", str(app_src)],
        "The downloaded update has an invalid signature",
    )
    info = subprocess.run(
        ["codesign", "-dvv", str(app_src)], capture_output=True, text=True, encoding="utf-8"
    )
    if f"TeamIdentifier={team}" not in (info.stderr or "") + (info.stdout or ""):
        raise UpdateError("The downloaded update is signed by an unexpected developer")
    plist = plistlib.loads((app_src / "Contents" / "Info.plist").read_bytes())
    got_version = str(plist.get("CFBundleShortVersionString") or "")
    if got_version != target_version:
        raise UpdateError(
            f"The downloaded update is version {got_version}, expected {target_version}"
        )
    return app_src


def _run_update(download_url: str, target_version: str, install_app: Path, team: str) -> None:
    tmp = Path(tempfile.mkdtemp(prefix="quodeq-selfupdate-"))
    mnt = _mountpoint_for_tests or (tmp / "mnt")
    mounted = False
    try:
        dmg = tmp / (Path(urlparse(download_url).path).name or "update.dmg")
        _download_file(download_url, dmg, lambda pct: _set(percent=pct))

        _set(phase="verifying", percent=100)
        _check(
            ["spctl", "-a", "-t", "open", "--context", "context:primary-signature", str(dmg)],
            "The downloaded update is not notarized by Apple",
        )
        _check(
            ["hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint", str(mnt), str(dmg)],
            "Could not open the downloaded update",
        )
        mounted = True
        app_src = _verify_mounted_app(mnt, install_app.name, team, target_version)

        _set(phase="installing")
        staging = install_app.parent / f".{install_app.name}.new"
        shutil.rmtree(staging, ignore_errors=True)
        _check(["ditto", str(app_src), str(staging)], "Could not copy the update into place")
        subprocess.run(["hdiutil", "detach", str(mnt)], capture_output=True, text=True, encoding="utf-8")
        mounted = False

        _swap_bundle(staging, install_app)
        _set(phase="relaunching", percent=100)
        _spawn_relauncher(install_app)
        _request_app_exit()
    except UpdateError as exc:
        _logger.warning("self-update failed: %s", exc)
        _set(phase="error", error=str(exc))
    except Exception:
        _logger.warning("self-update failed", exc_info=True)
        _set(phase="error", error="Automatic update failed")
    finally:
        if mounted:
            subprocess.run(["hdiutil", "detach", str(mnt)], capture_output=True, text=True, encoding="utf-8")
        shutil.rmtree(tmp, ignore_errors=True)


def _swap_bundle(staging: Path, install_app: Path) -> None:
    """Atomically replace the installed bundle with the staged copy."""
    old = install_app.parent / f".{install_app.name}.old-{os.getpid()}"
    os.rename(install_app, old)
    try:
        os.rename(staging, install_app)
    except Exception:
        os.rename(old, install_app)  # roll back so the app stays launchable
        raise
    shutil.rmtree(old, ignore_errors=True)


def _spawn_relauncher(install_app: Path) -> None:
    """Detached helper that reopens the app once this process has exited."""
    # The pid and app path are passed as positional parameters, never
    # interpolated into the script, so path contents cannot become shell.
    script = 'while kill -0 "$1" 2>/dev/null; do sleep 0.3; done; open -n "$2"'
    subprocess.Popen(
        ["/bin/sh", "-c", script, "_", str(os.getpid()), str(install_app)],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def cleanup_stale_staging(install_app: Path | None = None) -> None:
    """Remove leftovers from an interrupted update. Best-effort, call at startup."""
    try:
        app = install_app if install_app is not None else bundle_path()
        if app is None:
            return
        for leftover in list(app.parent.glob(f".{app.name}.old-*")) + [
            app.parent / f".{app.name}.new"
        ]:
            shutil.rmtree(leftover, ignore_errors=True)
    except Exception:
        _logger.debug("stale staging cleanup failed", exc_info=True)


def _reset_for_tests() -> None:
    global _thread
    _join_for_tests()
    with _lock:
        _progress.update(phase="idle", percent=0, error=None)
    _thread = None


def _join_for_tests() -> None:
    thread = _thread
    if thread is not None and thread.is_alive():
        thread.join(timeout=5)
