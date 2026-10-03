"""The process environment itself, as a config-layer seam.

Most env-backed settings resolve to one value and belong in a named getter
(``analysis_env``, ``clone_env``, ...). A few call sites need the WHOLE
mapping instead: a subprocess environment to filter and hand to ``Popen``,
or the credential source for a direct-API call whose variable name is only
known at runtime. Those sites take an injected ``env`` already; this module
is where their ``None`` default resolves, so the inner layers never name
``os.environ`` themselves.
"""
from __future__ import annotations

from collections.abc import Mapping
from quodeq.shared.env_resolve import resolve_env


def process_environment(env: Mapping[str, str] | None = None) -> Mapping[str, str]:
    """Return *env*, or the live process environment when it is None.

    An injected ``{}`` means "no variables set" and is returned as-is.
    """
    return resolve_env(env)


def process_environment_copy(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """A mutable copy of :func:`process_environment`.

    For callers that build a subprocess environment by stripping and adding
    keys: they must not mutate ``os.environ`` (or an injected mapping) in
    place.
    """
    return dict(process_environment(env))
