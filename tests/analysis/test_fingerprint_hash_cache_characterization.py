"""Characterization pin for ``_hash_standards`` output.

Locks the exact hash values ``_hash_standards`` produces BEFORE the
module-global ``functools.lru_cache`` machinery in ``fingerprint.py`` is
replaced by an injectable ``HashCache`` (TES-03 / C8). The hash VALUES a
cache-key-producing function returns must never shift as a caching-strategy
refactor detail -- a shifted value invalidates every cache entry a real
project has on disk. Each expected value is computed independently (plain
``hashlib.sha256`` on known bytes / composed strings), not by calling the
implementation, so the test is a real characterization oracle rather than a
tautology.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from quodeq.analysis import fingerprint
from quodeq.core.standards.overrides import OVERRIDES_RELPATH

_COMPILED_BODY = '{"id": "flexibility", "principles": []}'
# Independently computed: `printf '%s' '<body>' | shasum -a 256`.
_EXPECTED_BASE_HASH = "6da0aad60d8d5a65137a7955694c205db523cd5f8744fedc6ce8e323f4111311"


def _write_compiled(standards_dir: Path, dimension: str, body: str) -> None:
    compiled = standards_dir / "compiled"
    compiled.mkdir(parents=True, exist_ok=True)
    (compiled / f"{dimension}.json").write_text(body)


def test_hash_standards_pinned_output_no_project_root(tmp_path: Path):
    """No *project_root*: the hash is the plain SHA-256 of the compiled
    dimension JSON bytes -- both the literal pin and an independently
    computed oracle must agree with the implementation."""
    standards_dir = tmp_path / "standards"
    _write_compiled(standards_dir, "flexibility", _COMPILED_BODY)

    result = fingerprint._hash_standards(standards_dir, "flexibility")

    assert result == hashlib.sha256(_COMPILED_BODY.encode()).hexdigest()
    assert result == _EXPECTED_BASE_HASH


def test_hash_standards_pinned_output_with_overrides(tmp_path: Path):
    """With *project_root* overrides present, the hash is the SHA-256 of
    ``base\\x00overrides\\x00overrides_hash`` -- the exact composition
    ``_hash_standards`` documents, independently reproduced here."""
    standards_dir = tmp_path / "standards"
    _write_compiled(standards_dir, "flexibility", _COMPILED_BODY)
    project_root = tmp_path / "repo"
    project_root.mkdir()
    overrides_path = project_root / OVERRIDES_RELPATH
    overrides_path.parent.mkdir(parents=True, exist_ok=True)
    overrides_body = {"version": 1, "overrides": {"M-ANA-2": {"max_lines": 60}}}
    overrides_path.write_text(json.dumps(overrides_body))

    result = fingerprint._hash_standards(standards_dir, "flexibility", project_root)

    base = hashlib.sha256(_COMPILED_BODY.encode()).hexdigest()
    canonical_overrides = json.dumps(
        overrides_body["overrides"], sort_keys=True, separators=(",", ":"),
    )
    overrides_hash = hashlib.sha256(canonical_overrides.encode("utf-8")).hexdigest()
    expected = hashlib.sha256(
        f"{base}\x00overrides\x00{overrides_hash}".encode()
    ).hexdigest()

    assert result == expected
