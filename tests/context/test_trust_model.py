"""Tests for the declared project trust model."""
from __future__ import annotations

import json
import os
import sys

import pytest

from quodeq.context.trust_model import (
    CONSERVATIVE,
    PROFILE_RELPATH,
    TrustModel,
    resolve_trust_model,
)


def _write_profile(root, payload):
    path = root / PROFILE_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _desktop_manifest(root):
    (root / "pyproject.toml").write_text(
        '[project]\nname = "app"\ndependencies = ["pywebview>=6.2"]\n',
        encoding="utf-8",
    )


def test_absent_profile_and_no_manifest_is_conservative(tmp_path):
    # The no-regression guarantee: an undeclared, undetectable project is
    # scored exactly as it is today.
    assert resolve_trust_model(tmp_path) == CONSERVATIVE


def test_none_root_is_conservative():
    assert resolve_trust_model(None) == CONSERVATIVE


def test_declared_wins_over_detection(tmp_path):
    _desktop_manifest(tmp_path)  # detection would say loopback
    _write_profile(tmp_path, {"version": 1, "networkExposure": "public"})
    resolved = resolve_trust_model(tmp_path)
    assert resolved.network_exposure == "public"


def test_detection_fills_undeclared_fields(tmp_path):
    # Field-level fallback: declaring one axis must not blank the other.
    _desktop_manifest(tmp_path)
    _write_profile(tmp_path, {"version": 1, "networkExposure": "public"})
    assert resolve_trust_model(tmp_path).multi_tenant is False


def test_detection_used_when_no_profile(tmp_path):
    _desktop_manifest(tmp_path)
    resolved = resolve_trust_model(tmp_path)
    assert resolved.multi_tenant is False
    assert resolved.network_exposure == "loopback"


def test_library_does_not_relax(tmp_path):
    # A library's paths may be fed from an HTTP request in the consuming app,
    # and the author cannot know. It must declare to get the relaxation.
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "lib"\ndependencies = []\n', encoding="utf-8")
    assert resolve_trust_model(tmp_path) == CONSERVATIVE


@pytest.mark.parametrize("payload", [
    {"version": 2, "networkExposure": "loopback"},      # wrong version
    {"networkExposure": "loopback"},                     # missing version
    {"version": 1, "networkExposure": "carrier-pigeon"}, # unknown value
    {"version": 1, "multiTenant": "false"},              # wrong type
    [1, 2, 3],                                           # not an object
])
def test_malformed_profile_degrades_never_raises(tmp_path, payload):
    _write_profile(tmp_path, payload)
    assert resolve_trust_model(tmp_path) == CONSERVATIVE


def test_unreadable_profile_degrades(tmp_path):
    path = tmp_path / PROFILE_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert resolve_trust_model(tmp_path) == CONSERVATIVE


def test_unknown_keys_are_ignored(tmp_path):
    _write_profile(tmp_path, {
        "version": 1, "networkExposure": "loopback", "futureField": 42})
    assert resolve_trust_model(tmp_path).network_exposure == "loopback"


def test_lan_behaves_as_public_for_relaxation(tmp_path):
    _write_profile(tmp_path, {"version": 1, "networkExposure": "lan"})
    resolved = resolve_trust_model(tmp_path)
    assert resolved.network_exposure == "lan"   # recorded faithfully
    assert resolved.relaxes_remote() is False   # but grants nothing


def test_loopback_relaxes():
    assert TrustModel(multi_tenant=False, network_exposure="loopback").relaxes_remote() is True


@pytest.mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0,
    reason="chmod-based unreadability is meaningless on Windows or as root",
)
def test_permission_denied_profile_degrades(tmp_path):
    # Distinct from malformed JSON content: this is a genuine OS-level read
    # failure (the file is well-formed and never even gets parsed).
    path = tmp_path / PROFILE_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "networkExposure": "loopback"}), encoding="utf-8")
    os.chmod(path, 0o000)
    try:
        assert resolve_trust_model(tmp_path) == CONSERVATIVE
    finally:
        os.chmod(path, 0o644)
