"""Per-verification audit-log directory writer.

Writes four files into `<root>/<verification_id>/`:
  - manifest.json    - the resolver-built Manifest (serialized via to_dict)
  - prompt.system.txt - the system prompt the model received
  - prompt.user.txt  - the per-finding user prompt
  - response.json    - the raw model JSON output (after schema enforcement)

This lets future-you replay any verification without re-running Ollama, and
gives the UI a deep-dive view into "why did the verifier say X?".
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quodeq.resolver.models import Manifest


def write_audit_log(
    root: Path,
    verification_id: str,
    manifest: Manifest,
    system_prompt: str,
    user_prompt: str,
    raw_response: dict[str, Any],
) -> Path:
    """Write the audit-log files for one verification.

    Returns the directory the files were written to.
    """
    log_dir = root / verification_id
    log_dir.mkdir(parents=True, exist_ok=True)

    (log_dir / "manifest.json").write_text(
        json.dumps(manifest.to_dict(), indent=2, default=str),
        encoding="utf-8",
    )
    (log_dir / "prompt.system.txt").write_text(system_prompt, encoding="utf-8")
    (log_dir / "prompt.user.txt").write_text(user_prompt, encoding="utf-8")
    (log_dir / "response.json").write_text(
        json.dumps(raw_response, indent=2),
        encoding="utf-8",
    )

    return log_dir
