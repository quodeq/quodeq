"""Fetch and cache OWASP ASVS Level 1 requirements into the standards directory.

Delegates to internal modules for network I/O and JSON parsing.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from quodeq.shared.utils import write_text, get_asvs_url, show_diff

from quodeq.config._asvs_network import (  # noqa: F401
    fetch_with_retry as _fetch_with_retry,
    verify_integrity as _verify_integrity,
    _DEFAULT_FETCH_TIMEOUT_S,
)
from quodeq.config._asvs_parser import parse_asvs_content as _parse_asvs_content  # noqa: F401

_ASVS_DEFAULT_LEVEL = 1
_ASVS_ALLOWED_HOSTS = frozenset({"raw.githubusercontent.com", "github.com", "owasp.org"})
_ASVS_OUTPUT_DIR = "asvs"
_ASVS_OUTPUT_FILE = "level1.json"

_DEFAULT_ASVS_VERSION = "4.0.3"


def _asvs_version(override: str | None = None, env: dict[str, str] | None = None) -> str:
    """Return the ASVS version string. *override* bypasses env for testing."""
    if override is not None:
        return override
    return (env or os.environ).get("QUODEQ_ASVS_VERSION", _DEFAULT_ASVS_VERSION)


def fetch_asvs_l1(
    standards_dir: Path,
    *,
    dry_run: bool = False,
    expected_hash: str | None = None,
    skip_integrity: bool | None = None,
) -> int:
    """Fetch OWASP ASVS L1 requirements and write to standards_dir/asvs/level1.json.

    Returns the number of requirements fetched.
    """
    url = get_asvs_url()
    parsed = urlparse(url)
    if parsed.hostname not in _ASVS_ALLOWED_HOSTS:
        raise ValueError(
            f"ASVS URL host {parsed.hostname!r} is not in the allowlist. "
            f"Allowed: {', '.join(sorted(_ASVS_ALLOWED_HOSTS))}"
        )
    content = _fetch_with_retry(url)
    _verify_integrity(content, expected_hash, skip_integrity)
    requirements = _parse_asvs_content(content)

    output = {
        "source": f"OWASP ASVS {_asvs_version()}",
        "level": _ASVS_DEFAULT_LEVEL,
        "fetched": date.today().isoformat(),
        "requirements": requirements,
    }

    out_path = standards_dir / _ASVS_OUTPUT_DIR / _ASVS_OUTPUT_FILE
    if dry_run:
        show_diff(out_path, json.dumps(output, indent=2))
    else:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_text(out_path, json.dumps(output, indent=2))

    return len(requirements)
