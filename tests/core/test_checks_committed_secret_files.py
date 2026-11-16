"""Committed credential files are reported locally, with the value masked."""
import pytest

from quodeq.core.checks.hardcoded_secrets import (
    COMMITTED_FILE_VIOLATION_TYPE as VIOLATION_TYPE, REQ, check_committed_secret_files,
)
from quodeq.core.secret_files import KIND_ASSIGNMENTS, KIND_CREDENTIAL, KIND_PRIVATE_KEY
from quodeq.core.types.severity import Severity
from tests.core._fake_secrets import AWS_KEY, GENERIC_VALUE, PEM


def _check(*files):
    return check_committed_secret_files(files, dimension="security")


def test_env_with_a_credential_is_a_critical_violation_without_its_value():
    [j] = _check((".env", KIND_ASSIGNMENTS, f"PORT=3000\nDB_PASSWORD={GENERIC_VALUE}\n"))
    assert (j.req, j.file, j.line, j.severity) == (REQ, ".env", 2, Severity.CRITICAL)
    assert j.violation_type == VIOLATION_TYPE
    assert GENERIC_VALUE not in j.snippet and j.snippet.startswith("DB_PASSWORD=")


def test_npm_auth_token_and_known_token_formats_count():
    found = _check((".npmrc", KIND_ASSIGNMENTS, f"//registry.npmjs.org/:_authToken={GENERIC_VALUE}\n"),
                   ("prod.env", KIND_ASSIGNMENTS, f"S3={AWS_KEY}\n"))
    assert [j.file for j in found] == [".npmrc", "prod.env"]


@pytest.mark.parametrize("text", [
    "PORT=3000\nDEBUG=true\n",
    "API_TOKEN=changeme\n",
    "API_TOKEN=${API_TOKEN}\n",
    "SECRET_KEY=\n",
])
def test_env_without_a_real_credential_is_not(text):
    assert _check((".env", KIND_ASSIGNMENTS, text)) == []


def test_pem_counts_only_with_a_private_key():
    cert = "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"
    found = _check(("cert.pem", KIND_PRIVATE_KEY, cert), ("tls.key", KIND_PRIVATE_KEY, PEM))
    assert [j.file for j in found] == ["tls.key"]
    assert "PRIVATE KEY" not in found[0].snippet


def test_credential_files_count_when_not_empty():
    found = _check(("id_rsa", KIND_CREDENTIAL, "\x00binary"), (".netrc", KIND_CREDENTIAL, "  \n"))
    assert [(j.file, j.line) for j in found] == [("id_rsa", 1)]
