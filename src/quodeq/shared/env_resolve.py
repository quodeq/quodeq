"""Leaf helper that resolves an optional injected environment mapping.

Every injectable env seam in the codebase spells the same fallback:
``os.environ if env is None else env``. Written inline, that ``os.environ``
is a process-environment read in whatever layer the seam lives in, which
the ratchet (``tools/check_env_reads.py``) flags and which makes the module
untestable without mutating the process. Routing the fallback through this
config-layer helper keeps the single read where it belongs.

Never fall back on truthiness: an injected ``{}`` means "no variables
set", and ``or`` would hand back the real environment instead. That
spelling is gated separately by tests/tools/test_no_env_or_fallback.py.

Like ``_env_sanitize``, this is a leaf with no imports of its own, so
``_config.py``/``text_io.py`` (which ``env.py`` itself imports) can use it
without an import cycle back through ``env.py``.
"""
from __future__ import annotations

import os
from collections.abc import Mapping, MutableMapping


def resolve_env(env: Mapping[str, str] | None = None) -> Mapping[str, str]:
    """Return *env*, or the process environment when *env* is ``None``.

    An injected empty mapping is returned unchanged -- it means "no
    variables set", not "fall back to the process".
    """
    return os.environ if env is None else env


def resolve_env_mut(env: MutableMapping[str, str] | None = None) -> MutableMapping[str, str]:
    """``resolve_env`` for the few callers that WRITE back into the mapping.

    Separate from ``resolve_env`` only for the type: ``os.environ`` is a
    ``MutableMapping``, and a caller that assigns (``environ["PATH"] = ...``)
    needs that in its signature so an injected read-only mapping is a type
    error rather than a runtime one.
    """
    return os.environ if env is None else env
