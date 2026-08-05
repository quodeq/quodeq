"""Tests for the declared project trust model."""
from __future__ import annotations

import json
import os
import sys

import pytest

from quodeq.analysis.mcp.scope_gate import apply_scope_gate
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
    # Detection alone would never say loopback for exposure (see C1 below) --
    # this pins that a declared exposure wins over whatever multiTenant
    # detection contributes too.
    _desktop_manifest(tmp_path)
    _write_profile(tmp_path, {"version": 1, "networkExposure": "public"})
    resolved = resolve_trust_model(tmp_path)
    assert resolved.network_exposure == "public"


def test_detection_fills_undeclared_fields(tmp_path):
    # Field-level fallback: declaring one axis must not blank the other.
    _desktop_manifest(tmp_path)
    _write_profile(tmp_path, {"version": 1, "networkExposure": "public"})
    assert resolve_trust_model(tmp_path).multi_tenant is False


def test_detection_used_when_no_profile(tmp_path):
    # multi_tenant is safe to infer from a manifest. network_exposure is not
    # (see C1 tests below) and falls back to the conservative default even
    # though detection confidently says "desktop".
    _desktop_manifest(tmp_path)
    resolved = resolve_trust_model(tmp_path)
    assert resolved.multi_tenant is False
    assert resolved.network_exposure == "public"


def test_desktop_detection_alone_never_relaxes_remote(tmp_path):
    # C1: detection may fill multi_tenant but must NEVER fill
    # network_exposure -- only a human declaration in
    # .quodeq/project-profile.json may waive a remote-reachability finding.
    # A real Rust axum service (src/main.rs, no lib.rs) or a Django service
    # that merely lists pyinstaller in a dev extra both detect as
    # desktop/cli today; none of them may get S-AUT-3 waived on that basis
    # alone.
    _desktop_manifest(tmp_path)
    resolved = resolve_trust_model(tmp_path)
    assert resolved.network_exposure == "public"
    assert resolved.relaxes_remote() is False

    finding = {
        "t": "violation", "req": "S-AUT-3", "severity": "major",
        "w": "Path traversal via job_id",
        "reason": "The job_id is used to construct a file path without validation.",
    }
    assert apply_scope_gate(finding, resolved) is False
    assert finding["severity"] == "major"


def test_cli_detection_alone_never_relaxes_remote(tmp_path):
    # Same guarantee via the CLI detection path (a Go service with no web
    # framework import detects as a single-user CLI).
    (tmp_path / "go.mod").write_text("module example.com/tool\n\ngo 1.21\n", encoding="utf-8")
    (tmp_path / "main.go").write_text("package main\n\nfunc main() {}\n", encoding="utf-8")
    resolved = resolve_trust_model(tmp_path)
    assert resolved.multi_tenant is False
    assert resolved.network_exposure == "public"
    assert resolved.relaxes_remote() is False

    finding = {
        "t": "violation", "req": "S-AUT-3", "severity": "major",
        "w": "Path traversal via job_id",
        "reason": "The job_id is used to construct a file path without validation.",
    }
    assert apply_scope_gate(finding, resolved) is False
    assert finding["severity"] == "major"


def test_library_does_not_relax(tmp_path):
    # A library's paths may be fed from an HTTP request in the consuming app,
    # and the author cannot know. It must declare to get the relaxation.
    # A real Rust library fixture (has src/lib.rs, no src/main.rs, publish
    # not explicitly false), not merely a manifest that fails every other
    # detection route -- the old fixture here detected as UNKNOWN, not
    # LIBRARY, and coincidentally landed on the same CONSERVATIVE result.
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "mylib"\nversion = "0.1.0"\n', encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "lib.rs").write_text("pub fn hello() {}\n", encoding="utf-8")

    from quodeq.context.project_shape import Deployment, detect_shape
    assert detect_shape(tmp_path).deployment is Deployment.LIBRARY, (
        "fixture must actually detect as a library, or this test proves nothing"
    )
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


def test_multi_tenant_zero_is_rejected_not_coerced(tmp_path):
    # {"multiTenant": "false"} above is rejected by isinstance(), but a
    # bool()-coercing mutant would ALSO reject it (bool("false") is True,
    # same result as the correct CONSERVATIVE fallback of True) -- that
    # existing test cannot tell the two implementations apart. 0 is falsy:
    # bool(0) is False, which a mutant would happily accept as a declared
    # multiTenant=False, while the correct isinstance() check rejects it and
    # falls back to CONSERVATIVE's True. Pairing it with a valid
    # networkExposure keeps that axis out of the way of the assertion.
    _write_profile(tmp_path, {"version": 1, "multiTenant": 0, "networkExposure": "loopback"})
    resolved = resolve_trust_model(tmp_path)
    assert resolved.multi_tenant is True
    assert resolved.network_exposure == "loopback"


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


def test_deeply_nested_profile_degrades(tmp_path):
    # Bracket nesting deep enough to overflow the C JSON decoder's recursion
    # limit raises RecursionError, a RuntimeError subclass that the narrow
    # (OSError, ValueError, UnicodeDecodeError) catch does not cover. This is
    # advisory data with a conservative fallback, so it must degrade like any
    # other malformed profile, never escape and fail the scan.
    path = tmp_path / PROFILE_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[" * 80000 + "]" * 80000, encoding="utf-8")
    assert resolve_trust_model(tmp_path) == CONSERVATIVE


def test_declared_false_overrides_detected_true(tmp_path):
    # A falsy declared value must still win over a truthy detected one. Without
    # this, an `or`-chained resolution would pass the whole suite.
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "svc"\ndependencies = ["flask>=3.0"]\n', encoding="utf-8")
    _write_profile(tmp_path, {"version": 1, "multiTenant": False})
    assert resolve_trust_model(tmp_path).multi_tenant is False


def test_boolean_version_is_rejected(tmp_path):
    # bool is a subclass of int in Python, so True == 1: a naive
    # `!= SUPPORTED_VERSION` check would accept "version": true as version 1.
    _write_profile(tmp_path, {"version": True, "networkExposure": "loopback"})
    assert resolve_trust_model(tmp_path) == CONSERVATIVE


def test_deeply_nested_package_json_degrades(tmp_path):
    # Same RecursionError overflow as the declared-side fix, but reached
    # through detection: detect_shape parses package.json via _read_json,
    # whose except json.JSONDecodeError does not catch RecursionError (a
    # RuntimeError subclass). _detected_fields must degrade this too, not
    # just the declared-profile path.
    (tmp_path / "package.json").write_text(
        "[" * 80000 + "]" * 80000, encoding="utf-8")
    assert resolve_trust_model(tmp_path) == CONSERVATIVE


def test_deeply_nested_pyproject_toml_degrades(tmp_path):
    # Same class of bug, via tomllib on the pyproject.toml detection path.
    (tmp_path / "pyproject.toml").write_text(
        "a = " + "[" * 5000 + "]" * 5000, encoding="utf-8")
    assert resolve_trust_model(tmp_path) == CONSERVATIVE
