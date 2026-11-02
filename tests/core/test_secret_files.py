"""Which file names count as credential files."""
import pytest

from quodeq.core.secret_files import (
    KIND_ASSIGNMENTS, KIND_CREDENTIAL, KIND_PRIVATE_KEY, secret_file_kind,
)


@pytest.mark.parametrize(("name", "kind"), [
    (".env", KIND_ASSIGNMENTS), (".env.production", KIND_ASSIGNMENTS),
    ("prod.env", KIND_ASSIGNMENTS), (".npmrc", KIND_ASSIGNMENTS),
    ("server.pem", KIND_PRIVATE_KEY), ("TLS.KEY", KIND_PRIVATE_KEY),
    ("id_ed25519", KIND_CREDENTIAL), (".git-credentials", KIND_CREDENTIAL),
    ("release.keystore", KIND_CREDENTIAL),
])
def test_credential_files_are_recognised(name, kind):
    assert secret_file_kind(name) == kind


@pytest.mark.parametrize("name", [
    ".env.example", ".env.sample", "config.env.template", ".npmrc.dist",
    "id_ed25519.pub", "env.py", "keys.py", "settings.json",
])
def test_templates_public_keys_and_code_are_not(name):
    assert secret_file_kind(name) is None
