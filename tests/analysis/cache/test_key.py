"""Cache key — stability, sensitivity, and the permissive field set.

The V2 cache key is permissive (cost-first): it invalidates ONLY on real
per-unit changes — file content, file path, dimension, language. Volatile
inputs (model, prompts, standards, sampling params) are deliberately NOT in
the key; they are recorded in ``CacheEntry.provenance`` so reuse across those
boundaries is surfaced, not silently re-evaluated.
"""
from __future__ import annotations

import dataclasses

from quodeq.analysis.cache.key import CacheKey, compute_key


def _base_key(**overrides) -> CacheKey:
    defaults = dict(
        schema_version=3,
        file_content_hash="aa" * 32,
        file_path="src/auth.py",
        dimension="security",
        language="python",
    )
    defaults.update(overrides)
    return CacheKey(**defaults)


class TestPermissiveFieldSet:
    def test_key_holds_only_file_change_fields(self):
        # Structural guard: this is the contract. If a volatile field
        # (model_id, prompts_hash, standards_hash, temperature, ...) is ever
        # re-added to the key, this fails loudly — that is a cache-wide
        # re-eval the user did not ask for.
        assert {f.name for f in dataclasses.fields(CacheKey)} == {
            "schema_version",
            "file_content_hash",
            "file_path",
            "dimension",
            "language",
        }


class TestStability:
    def test_same_inputs_same_key(self):
        assert compute_key(_base_key()) == compute_key(_base_key())

    def test_field_declaration_order_does_not_affect_key(self):
        # CacheKey is frozen and the canonicalization sorts keys, so a key
        # built piecewise in any order produces the same hash.
        k1 = _base_key()
        k2 = CacheKey(
            file_content_hash="aa" * 32,
            file_path="src/auth.py",
            dimension="security",
            language="python",
            schema_version=3,
        )
        assert compute_key(k1) == compute_key(k2)


class TestSensitivity:
    def test_file_content_change_invalidates(self):
        a = compute_key(_base_key(file_content_hash="00" * 32))
        b = compute_key(_base_key(file_content_hash="ff" * 32))
        assert a != b

    def test_dimension_change_invalidates(self):
        a = compute_key(_base_key(dimension="security"))
        b = compute_key(_base_key(dimension="documentation"))
        assert a != b

    def test_language_change_invalidates(self):
        # Language stays in the key: it is a stable project property, and
        # changing it genuinely changes which files exist and how they are
        # analyzed.
        a = compute_key(_base_key(language="python"))
        b = compute_key(_base_key(language="kotlin"))
        assert a != b

    def test_schema_version_change_invalidates(self):
        assert compute_key(_base_key(schema_version=2)) != compute_key(_base_key(schema_version=3))

    def test_path_change_invalidates(self):
        # Path-sensitive rules (e.g. src/ vs tests/) must produce distinct keys.
        assert compute_key(_base_key(file_path="src/a.py")) != compute_key(_base_key(file_path="tests/a.py"))


class TestKeyShape:
    def test_returns_64_char_hex(self):
        h = compute_key(_base_key())
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)
