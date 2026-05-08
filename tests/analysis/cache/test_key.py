"""Cache key — stability and sensitivity properties."""
from __future__ import annotations

from quodeq.analysis.cache.key import CacheKey, compute_key


def _base_key(**overrides) -> CacheKey:
    defaults = dict(
        schema_version=1,
        file_content_hash="aa" * 32,
        file_path="src/auth.py",
        dimension="security",
        standards_hash="bb" * 32,
        prompts_hash="cc" * 32,
        evaluator_hash="dd" * 32,
        model_id="claude-opus-4-7",
        language="python",
        temperature=None,
        max_tokens=None,
    )
    defaults.update(overrides)
    return CacheKey(**defaults)


class TestStability:
    def test_same_inputs_same_key(self):
        assert compute_key(_base_key()) == compute_key(_base_key())

    def test_field_declaration_order_does_not_affect_key(self):
        # CacheKey is frozen and the canonicalization sorts keys, so a key
        # built piecewise in any order produces the same hash.
        k1 = _base_key(model_id="claude-sonnet-4-6")
        k2 = CacheKey(
            schema_version=1, file_content_hash="aa" * 32, file_path="src/auth.py",
            dimension="security", standards_hash="bb" * 32, prompts_hash="cc" * 32,
            evaluator_hash="dd" * 32, language="python", model_id="claude-sonnet-4-6",
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

    def test_standards_change_invalidates(self):
        assert compute_key(_base_key(standards_hash="11" * 32)) != compute_key(_base_key(standards_hash="22" * 32))

    def test_prompts_change_invalidates(self):
        assert compute_key(_base_key(prompts_hash="11" * 32)) != compute_key(_base_key(prompts_hash="22" * 32))

    def test_evaluator_change_invalidates(self):
        assert compute_key(_base_key(evaluator_hash="11" * 32)) != compute_key(_base_key(evaluator_hash="22" * 32))

    def test_model_change_invalidates(self):
        assert compute_key(_base_key(model_id="claude-opus-4-7")) != compute_key(_base_key(model_id="claude-sonnet-4-6"))

    def test_schema_version_change_invalidates(self):
        assert compute_key(_base_key(schema_version=1)) != compute_key(_base_key(schema_version=2))

    def test_temperature_change_invalidates(self):
        assert compute_key(_base_key(temperature=None)) != compute_key(_base_key(temperature=0.7))

    def test_max_tokens_change_invalidates(self):
        assert compute_key(_base_key(max_tokens=None)) != compute_key(_base_key(max_tokens=4096))

    def test_path_change_invalidates(self):
        # Path-sensitive rules (e.g. src/ vs tests/) must produce distinct keys.
        assert compute_key(_base_key(file_path="src/a.py")) != compute_key(_base_key(file_path="tests/a.py"))


class TestKeyShape:
    def test_returns_64_char_hex(self):
        h = compute_key(_base_key())
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)
