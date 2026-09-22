"""Unit tests for validate_canonical_absolute and relative_scope_error
(shared/validation.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.shared.validation import (
    relative_scope_error,
    validate_canonical_absolute,
    validate_relative_scope,
)


class TestValidateCanonicalAbsolute:
    def test_absolute_happy_path(self, tmp_path):
        resolved = validate_canonical_absolute(str(tmp_path))
        assert resolved == tmp_path.resolve()
        assert isinstance(resolved, Path)

    def test_returns_resolved_canonical_form(self, tmp_path):
        raw = str(tmp_path) + "/./sub"
        assert validate_canonical_absolute(raw) == (tmp_path / "sub").resolve()

    def test_rejects_relative_path(self):
        with pytest.raises(ValueError, match="absolute"):
            validate_canonical_absolute("some/relative/path")

    def test_rejects_literal_parent_segment(self, tmp_path):
        # Even when it would resolve to a fine canonical location.
        with pytest.raises(ValueError, match="parent-directory"):
            validate_canonical_absolute(str(tmp_path / "sub" / ".." / "other"))

    def test_rejects_relative_parent_segment(self):
        with pytest.raises(ValueError, match="parent-directory"):
            validate_canonical_absolute("../escape")


class TestRelativeScopeError:
    """Parity between relative_scope_error and validate_relative_scope: the
    checker must return exactly the message the raising twin raises."""

    @pytest.mark.parametrize(
        "bad", ["../x", "a/../../b", "/abs", "C:evil", "a\\b", "a\0b"]
    )
    def test_matches_raised_message(self, bad):
        with pytest.raises(ValueError) as excinfo:
            validate_relative_scope(bad)
        assert relative_scope_error(bad) == str(excinfo.value)

    @pytest.mark.parametrize(
        "good", ["src", "src/backend", "a.b/c-d_e", "src/with..dots"]
    )
    def test_none_for_valid_scope(self, good):
        assert relative_scope_error(good) is None
        validate_relative_scope(good)  # must not raise
