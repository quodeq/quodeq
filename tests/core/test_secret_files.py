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


@pytest.mark.parametrize(("name", "kind"), [
    ("id_rsa_old", KIND_CREDENTIAL), ("id_rsa.bak", KIND_CREDENTIAL), ("id_dsa~", KIND_CREDENTIAL),
    ("id_ecdsa-work", KIND_CREDENTIAL), ("ID_ED25519.backup", KIND_CREDENTIAL),
    (".netrc.bak", KIND_CREDENTIAL), (".pgpass.old", KIND_CREDENTIAL),
    (".git-credentials.orig", KIND_CREDENTIAL), (".htpasswd-staging", KIND_CREDENTIAL),
    (".npmrc.backup", KIND_ASSIGNMENTS), (".pypirc~", KIND_ASSIGNMENTS),
])
def test_a_backup_or_renamed_copy_is_the_same_credential(name, kind):
    assert secret_file_kind(name) == kind


@pytest.mark.parametrize("name", [
    "id_rsa.pub", "id_dsa.pub", "id_ecdsa.pub", "id_rsa_old.pub",   # public halves
    ".netrc.example", ".pgpass.sample", "id_rsa.template", ".pypirc.dist",  # templates
    "identity.py", "idrsa.py", "netrc.py", "htpasswd.py", "npmrc.md",  # ordinary files
])
def test_public_keys_templates_and_source_stay_readable(name):
    assert secret_file_kind(name) is None
