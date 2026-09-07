"""Cache key — stability, sensitivity, and the permissive field set.

The V2 cache key is permissive (cost-first): it invalidates ONLY on real
per-unit changes — file content, file path, dimension, non-default params.
Volatile inputs (model, prompts, standards, sampling params) and, since
schema 4, the project language are deliberately NOT in the key; they are
recorded in ``CacheEntry.provenance`` so reuse across those boundaries is
surfaced, not silently re-evaluated.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json

from quodeq.analysis.cache.key import CacheKey, compute_key


def _base_key(**overrides) -> CacheKey:
    defaults = dict(
        schema_version=4,
        file_content_hash="aa" * 32,
        file_path="src/auth.py",
        dimension="security",
    )
    defaults.update(overrides)
    return CacheKey(**defaults)


class TestPermissiveFieldSet:
    def test_key_holds_only_file_change_fields(self):
        # Structural guard: this is the contract. If a volatile field
        # (model_id, prompts_hash, standards_hash, language, temperature, ...)
        # is ever re-added to the key, this fails loudly — that is a
        # cache-wide re-eval the user did not ask for.
        assert {f.name for f in dataclasses.fields(CacheKey)} == {
            "schema_version",
            "file_content_hash",
            "file_path",
            "dimension",
            "params_hash",
        }

    def test_schema_version_is_4_and_exported_from_data_layer(self):
        from quodeq.data.cache_store.key import SCHEMA_VERSION
        from quodeq.data.cache_store.key import CacheKey as DataCacheKey
        assert SCHEMA_VERSION == 4
        assert DataCacheKey is CacheKey


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
            schema_version=4,
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

    def test_schema_version_change_invalidates(self):
        assert compute_key(_base_key(schema_version=3)) != compute_key(_base_key(schema_version=4))

    def test_path_change_invalidates(self):
        # Path-sensitive rules (e.g. src/ vs tests/) must produce distinct keys.
        assert compute_key(_base_key(file_path="src/a.py")) != compute_key(_base_key(file_path="tests/a.py"))


class TestKeyShape:
    def test_returns_64_char_hex(self):
        h = compute_key(_base_key())
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


class TestParamsHash:
    def test_empty_params_hash_is_omitted_from_canonical_form(self):
        # An empty params_hash serializes identically to a key with no
        # params_hash member at all, so default-config keys never shift when
        # the params feature is a no-op for a project.
        key = _base_key()
        canonical = json.dumps(
            {
                "dimension": "security",
                "file_content_hash": "aa" * 32,
                "file_path": "src/auth.py",
                "schema_version": 4,
            },
            sort_keys=True, separators=(",", ":"),
        )
        expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        assert compute_key(key) == expected

    def test_non_empty_params_hash_changes_key(self):
        assert compute_key(_base_key(params_hash="ff" * 32)) != compute_key(_base_key())

    def test_distinct_params_hashes_yield_distinct_keys(self):
        a = compute_key(_base_key(params_hash="aa" * 32))
        b = compute_key(_base_key(params_hash="bb" * 32))
        assert a != b

    def test_reverting_params_hash_restores_original_key(self):
        original = compute_key(_base_key())
        assert compute_key(_base_key(params_hash="")) == original
