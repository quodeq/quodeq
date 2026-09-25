"""Version comparison built on packaging.version, pre-release-safe."""

from __future__ import annotations

from packaging.version import InvalidVersion, Version

_VERSION_PREFIX_CHARS = ("v", "V")  # leading char a release tag may drop


def normalize(version: str) -> str:
    """Strip a leading ``v`` and surrounding whitespace off a release tag."""
    v = version.strip()
    if v[:1] in _VERSION_PREFIX_CHARS:
        v = v[1:]
    return v


def is_newer(installed: str | None, latest: str | None) -> bool:
    """True only when *latest* is a strictly-greater FINAL release than *installed*."""
    if not installed or not latest:
        return False
    try:
        latest_v = Version(normalize(latest))
        installed_v = Version(normalize(installed))
    except InvalidVersion:
        return False
    if latest_v.is_prerelease:
        return False
    return latest_v > installed_v
