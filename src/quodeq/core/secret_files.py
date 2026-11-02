"""Files that exist to hold credentials, recognised by name.

An agent CLI reads files itself, so prompt redaction (``core.secret_scan``)
never sees what it reads. These files are kept from it instead: the OS
sandbox and the CLI's own permission rules deny reading them. A credential
written inline in ordinary source still reaches the model, since judging the
code means reading it.

Being unreadable to the agent must not hide a committed one, so the
``committed-secret-files`` half of the hardcoded-secrets check reports them
locally, without any model.
"""
from __future__ import annotations

from fnmatch import fnmatchcase

# What each kind of file needs before it counts as a committed secret.
KIND_ASSIGNMENTS = "assignments"  # KEY=value pairs: only credential-named keys with a value
KIND_PRIVATE_KEY = "private_key"  # .pem/.key: also hold public certificates
KIND_CREDENTIAL = "credential"    # the whole file is a credential

_GLOBS: tuple[tuple[str, str], ...] = (
    (".env", KIND_ASSIGNMENTS), (".env.*", KIND_ASSIGNMENTS), ("*.env", KIND_ASSIGNMENTS),
    (".npmrc", KIND_ASSIGNMENTS), (".pypirc", KIND_ASSIGNMENTS),
    ("*.pem", KIND_PRIVATE_KEY), ("*.key", KIND_PRIVATE_KEY),
    ("*.p12", KIND_CREDENTIAL), ("*.pfx", KIND_CREDENTIAL),
    ("*.jks", KIND_CREDENTIAL), ("*.keystore", KIND_CREDENTIAL),
    ("id_rsa", KIND_CREDENTIAL), ("id_dsa", KIND_CREDENTIAL),
    ("id_ecdsa", KIND_CREDENTIAL), ("id_ed25519", KIND_CREDENTIAL),
    (".netrc", KIND_CREDENTIAL), (".git-credentials", KIND_CREDENTIAL),
    (".pgpass", KIND_CREDENTIAL), (".htpasswd", KIND_CREDENTIAL),
)

# Templates checked in on purpose, with placeholder values: readable.
_TEMPLATE_SUFFIXES = (".example", ".sample", ".template", ".dist")

SECRET_FILE_GLOBS: tuple[str, ...] = tuple(glob for glob, _ in _GLOBS)


def secret_file_kind(name: str) -> str | None:
    """The kind of credential file *name* (a basename) is, or None."""
    lowered = name.lower()
    if lowered.endswith(_TEMPLATE_SUFFIXES):
        return None
    return next((kind for glob, kind in _GLOBS if fnmatchcase(lowered, glob)), None)
