"""Secret detection and typed-placeholder redaction (core.secret_scan)."""
from __future__ import annotations

import pytest

from quodeq.core.secret_scan import find_secrets, placeholder, redact
from tests.core._fake_secrets import (
    ANTHROPIC_KEY, AWS_KEY, GENERIC_VALUE, GITHUB_TOKEN, OPENAI_KEY, PEM,
)


@pytest.mark.parametrize(("line", "kind"), [
    (f'KEY = "{AWS_KEY}"', "aws_access_key"),
    (f"token: {GITHUB_TOKEN}", "github_token"),
    (f'client = OpenAI(api_key="{OPENAI_KEY}")', "openai_api_key"),
    (f"ANTHROPIC={ANTHROPIC_KEY}", "anthropic_api_key"),
    (f'db_password = "{GENERIC_VALUE}"', "generic_secret"),
    (f'"apiKey": "{GENERIC_VALUE}"', "generic_secret"),
])
def test_detects_each_kind(line, kind):
    assert [h.kind for h in find_secrets(line)] == [kind]


@pytest.mark.parametrize("line", [
    'password = "changeme"',                          # too short
    'password = os.environ["DB_PASSWORD"]',           # not a literal
    'token = "${GITHUB_TOKEN_FROM_THE_ENVIRONMENT}"',  # interpolation
    'secret = "aaaaaaaaaaaaaaaaaaaaaaaa"',            # no entropy
    'colour = "q8Zr4Lm2Vx9Tn6Wb3q8Zr4Lm2"',           # name is not a credential
    "className = 'sk-loading-spinner-container'",    # sk- word, no digits
])
def test_ignores_near_misses(line):
    assert find_secrets(line) == []


@pytest.mark.parametrize("line", [
    f"DB_PASSWORD={GENERIC_VALUE}",
    f"export API_TOKEN={GENERIC_VALUE}",
    f"  secret_key: {GENERIC_VALUE}",
    f"spring.datasource.password = {GENERIC_VALUE}  # prod",
    f"      - POSTGRES_PASSWORD={GENERIC_VALUE}",
    f"ENV AUTH_TOKEN={GENERIC_VALUE}",
    f"JWT_SECRET={GENERIC_VALUE}\r",
])
def test_detects_an_unquoted_value_on_a_line_of_its_own(line):
    (hit,) = find_secrets(f"FIRST=1\n{line}\nLAST=2\n")
    assert (hit.kind, hit.line) == ("generic_secret", 2)
    assert f"FIRST=1\n{line}\nLAST=2\n"[hit.start:hit.end] == GENERIC_VALUE


@pytest.mark.parametrize("line", [
    "token = oauth2_access_token_v2_2024",                       # an identifier
    "password = hashlib.sha256(raw_password_123).hexdigest()",  # a call
    f"login(password={GENERIC_VALUE})",                          # not the whole line
    f"token = {GENERIC_VALUE};",                                 # a statement
    "secretName: tls-2024-prod-cert",                            # names a secret, is not one
    f"PRIVATE_KEY_PATH=/run/keys/{GENERIC_VALUE}",               # points at one
    "token_url=https://auth.example.com/oauth2/v2/token/2024",   # a URL
    "API_TOKEN=${API_TOKEN_FROM_VAULT_2024}",                    # interpolation
    "PASSWORD=changeme-changeme-1",                              # a placeholder word
    "DB_PASSWORD=aaaaaaaa11111111aaaaaaaa",                      # no entropy
    f"COLOUR={GENERIC_VALUE}",                                   # name is not a credential
])
def test_ignores_unquoted_near_misses(line):
    assert find_secrets(line) == []


def test_redacting_an_env_file_keeps_keys_and_line_count():
    text = f"# settings\nDEBUG=true\nDB_PASSWORD={GENERIC_VALUE}\nPORT=8080\n"
    redacted = redact(text)
    assert redacted == f"# settings\nDEBUG=true\nDB_PASSWORD={placeholder('generic_secret')}\nPORT=8080\n"
    assert redact(redacted) == redacted


def test_hit_reports_the_line_and_exact_span():
    text = f"a = 1\nb = '{AWS_KEY}'\n"
    (hit,) = find_secrets(text)
    assert hit.line == 2
    assert text[hit.start:hit.end] == AWS_KEY


def test_redact_swaps_the_value_for_a_typed_placeholder():
    redacted = redact(f'KEY = "{AWS_KEY}"  # prod')
    assert redacted == f'KEY = "{placeholder("aws_access_key")}"  # prod'
    assert AWS_KEY not in redacted


def test_redact_keeps_a_multiline_key_at_the_same_line_count():
    text = f"before\n{PEM}\nafter = 1\n"
    redacted = redact(text)
    assert "MIIEow" not in redacted
    assert redacted.count("\n") == text.count("\n")
    assert redacted.splitlines()[1] == placeholder("private_key")
    assert redacted.splitlines().index("after = 1") == text.splitlines().index("after = 1")


def test_a_key_without_its_end_marker_is_masked_to_the_end():
    """A context window can cut a PEM block in half."""
    head = "\n".join(PEM.splitlines()[:2])
    assert "MIIEow" not in redact(head)


def test_redact_is_idempotent_and_leaves_clean_text_alone():
    once = redact(f'pwd = "{GENERIC_VALUE}"')
    assert redact(once) == once
    assert redact("x = 1\n") == "x = 1\n"
    assert redact("") == ""
