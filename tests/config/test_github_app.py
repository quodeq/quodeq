from quodeq.config.github_app import (
    DEFAULT_GITHUB_CLIENT_ID, GITHUB_CLIENT_ID_ENV, GITHUB_HOST, GITHUB_OAUTH_SCOPE, github_client_id,
)


def test_client_id_env_override():
    assert github_client_id({GITHUB_CLIENT_ID_ENV: "Iv1.abc"}) == "Iv1.abc"
    assert github_client_id({}) == DEFAULT_GITHUB_CLIENT_ID
    assert github_client_id({GITHUB_CLIENT_ID_ENV: "  "}) == DEFAULT_GITHUB_CLIENT_ID


def test_constants():
    assert GITHUB_HOST == "github.com"
    assert GITHUB_OAUTH_SCOPE == "repo"
