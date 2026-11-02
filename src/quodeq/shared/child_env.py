"""Allowlisted environments for agent CLI subprocesses."""
from __future__ import annotations

from collections.abc import Iterable, Mapping

# What any CLI needs to start, reach the network through a proxy and verify
# TLS. Everything else (GH_TOKEN, AWS_*, JIRA_API_TOKEN, ...) stays behind.
RUNTIME_ENV_KEYS = frozenset({
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "TERM", "TMPDIR", "TZ",
    "USERPROFILE", "APPDATA", "LOCALAPPDATA", "SYSTEMROOT", "SystemRoot",
    "WINDIR", "PATHEXT", "TEMP", "TMP",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy",
    "NODE_EXTRA_CA_CERTS", "SSL_CERT_FILE", "SSL_CERT_DIR",
})
_LOCALE_PREFIX = "LC_"


def allowlisted_env(env: Mapping[str, str], *, keys: Iterable[str] = (),
                    prefixes: Iterable[str] = ()) -> dict[str, str]:
    """The runtime keys of *env*, plus *keys* and anything starting with *prefixes*."""
    allowed = RUNTIME_ENV_KEYS | frozenset(keys)
    starts = (_LOCALE_PREFIX, *prefixes)
    return {k: v for k, v in env.items() if k in allowed or k.startswith(starts)}
