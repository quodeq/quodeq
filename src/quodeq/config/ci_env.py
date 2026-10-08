"""Where a CLI run came from, read from the GitHub Actions environment.

The parsing lives in ``core.run.origin`` (pure); this module only gathers
its inputs, the environment and the event payload file GitHub Actions
points to. Nothing here may fail a run: an unreadable or malformed payload
just leaves the PR number unknown.
"""
from __future__ import annotations

import json
import os
from collections.abc import Mapping

from quodeq.core.run.origin import RunOrigin, origin_from_env

_EVENT_PATH_ENV = "GITHUB_EVENT_PATH"


def _event_payload(env: Mapping[str, str]) -> object:
    """The parsed GitHub event payload, or None when absent or unreadable."""
    path = env.get(_EVENT_PATH_ENV)
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def current_run_origin(env: Mapping[str, str] | None = None) -> RunOrigin:
    """Where the run starting in this process came from."""
    env = os.environ if env is None else env
    return origin_from_env(env, _event_payload(env))
