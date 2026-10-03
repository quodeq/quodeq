import pytest

from quodeq.data.fs.repo_validation import validate_remote_url
from quodeq.shared.repo import is_repo_url


@pytest.mark.parametrize("url", ["https://github.com/o/r.git", "git@github.com:o/r.git", "ssh://git@github.com/o/r.git", "ssh://git@github.com:22/o/r.git"])
def test_accepted_schemes(url, monkeypatch):
    monkeypatch.setattr("quodeq.data.fs.repo_validation._resolves_to_private", lambda host: False)
    assert is_repo_url(url) is True
    validate_remote_url(url)  # no raise


def test_git_scheme_is_not_a_repo_url():
    assert is_repo_url("git://github.com/o/r.git") is False


def test_http_still_rejected():
    with pytest.raises(ValueError):
        is_repo_url("http://github.com/o/r.git")


@pytest.mark.parametrize("url", ["ssh://git@127.0.0.1/x", "ssh://git@127.0.0.1:2222/x.git"])
def test_private_ssh_host_rejected(url):
    with pytest.raises(ValueError):
        validate_remote_url(url)
