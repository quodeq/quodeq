"""Project archive format and size limits, shared by export and import.

The manifest ``kind``/``schema`` an export writes and an import checks, the
size cap on an archive, and the headroom the extracted contents may reach.
"""
from __future__ import annotations

from quodeq.shared.env import env_int

_DEFAULT_MAX_ZIP_SIZE_MB = 500
MANIFEST_KIND = "quodeq-project-export"
MANIFEST_SCHEMA = 1
# Import allows the extracted (uncompressed) archive to reach the MB cap times
# this multiple (evaluation data is text that deflates ~5x). Export applies the
# same bound so it never produces an archive that would fail re-import.
EXTRACT_HEADROOM = 10


def max_zip_size_bytes(max_mb: int | None = None, env: dict[str, str] | None = None) -> int:
    """Return the max zip export size in bytes.

    *max_mb* overrides the env var for testing. An unparseable
    QUODEQ_MAX_ZIP_SIZE_MB falls back to the default, with ``env_int``
    logging a warning that names the variable, the bad value and the
    default.
    """
    if max_mb is None:
        max_mb = env_int("QUODEQ_MAX_ZIP_SIZE_MB", _DEFAULT_MAX_ZIP_SIZE_MB, env=env)
    return max_mb * 1024 * 1024
