"""Unit tests for validate_canonical_absolute (shared/validation.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.shared.validation import validate_canonical_absolute


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
