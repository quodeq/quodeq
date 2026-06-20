"""Tests for the shared repo-URL SSRF validator (validate_remote_url)."""
import pytest

from quodeq.data.fs.repo_validation import validate_remote_url


class TestValidateRemoteUrlSsh:
    """git@host:path (scp-like) URLs must get the same private-host guard as
    https URLs. git clone of these drives SSH to the host, so an internal
    target is an SSRF/probe vector that must be rejected."""

    @pytest.mark.parametrize(
        "url",
        [
            "git@127.0.0.1:user/repo.git",
            "git@10.0.0.5:team/app.git",
            "git@192.168.1.10:x/y.git",
            "git@169.254.169.254:latest/meta.git",
            "git@localhost:user/repo.git",
        ],
    )
    def test_ssh_form_internal_host_rejected(self, url):
        with pytest.raises(ValueError):
            validate_remote_url(url)

    def test_ssh_form_encoded_loopback_rejected(self):
        # git's inet_aton reads 0177 as octal 127 -> dials 127.0.0.1 over SSH.
        with pytest.raises(ValueError):
            validate_remote_url("git@0177.0.0.1:user/repo.git")


class TestValidateRemoteUrlHttps:
    def test_https_loopback_rejected(self):
        with pytest.raises(ValueError):
            validate_remote_url("https://127.0.0.1/x.git")

    def test_https_link_local_metadata_rejected(self):
        with pytest.raises(ValueError):
            validate_remote_url("https://169.254.169.254/latest/meta-data")

    def test_https_octal_encoded_loopback_rejected(self):
        with pytest.raises(ValueError):
            validate_remote_url("https://0177.0.0.1/repo.git")

    def test_malformed_url_rejected(self):
        with pytest.raises(ValueError):
            validate_remote_url("not a url")
