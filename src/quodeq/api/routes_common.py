"""Shared helpers used across route modules."""
from __future__ import annotations

import os

from quodeq.shared.utils import get_evaluations_dir


def reports_dir() -> str:
    """Resolve the reports directory from server configuration.

    Takes no request input, deliberately. This used to accept an
    ``?evaluations=`` query parameter that repointed the entire reports root,
    guarded by a containment check against the configured directory. No
    client, test, or documented workflow ever sent it: every one of the 36
    call sites invokes ``reports_dir()`` bare. An unused parameter that
    redirects the storage root is attack surface with no upside, so it is
    gone rather than guarded.

    The consequence worth knowing: this value is now server-controlled, so
    every path built on top of it starts from a trusted root. Do not
    reintroduce a request-supplied override here. If a future feature needs
    multiple roots, resolve them from configuration and select by an opaque
    identifier, never by a caller-supplied path.
    """
    return os.path.realpath(get_evaluations_dir())
