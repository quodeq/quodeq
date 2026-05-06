"""API request payload compatibility for the incremental → clean_scan rename."""
import logging
from unittest.mock import patch
import pytest

from quodeq.api._evaluation_helpers import _build_evaluation_options
import quodeq.api._evaluation_helpers as _helpers_mod


def test_clean_scan_field_default_false():
    opts = _build_evaluation_options({})
    assert opts.clean_scan is False


def test_clean_scan_field_explicit_true():
    opts = _build_evaluation_options({"cleanScan": True})
    assert opts.clean_scan is True


def test_legacy_incremental_false_maps_to_clean_scan_true():
    """Legacy `incremental: false` (old "ignore cache") maps to `clean_scan: true`.

    Inverted semantics: the old flag was opt-in; the new flag is opt-out.
    """
    with patch.object(_helpers_mod._logger, "warning") as mock_warn:
        opts = _build_evaluation_options({"incremental": False})
    assert opts.clean_scan is True
    # Deprecation warning should fire on the helper module's logger.
    assert mock_warn.called, "Expected a deprecation warning for legacy `incremental` field"
    warn_msg = mock_warn.call_args[0][0]
    assert "deprecated" in warn_msg.lower()
    assert "incremental" in warn_msg.lower()


def test_legacy_incremental_true_maps_to_clean_scan_false():
    """Legacy `incremental: true` (old "use cache") maps to `clean_scan: false`."""
    with patch.object(_helpers_mod._logger, "warning") as mock_warn:
        opts = _build_evaluation_options({"incremental": True})
    assert opts.clean_scan is False
    assert mock_warn.called, "Expected a deprecation warning for legacy `incremental` field"
    warn_msg = mock_warn.call_args[0][0]
    assert "deprecated" in warn_msg.lower()
    assert "incremental" in warn_msg.lower()


def test_conflicting_fields_rejected():
    """Sending both fields is a ValueError — we don't guess intent."""
    with pytest.raises(ValueError, match="cannot be combined"):
        _build_evaluation_options({"incremental": True, "cleanScan": True})


def test_conflicting_fields_rejected_even_when_values_align():
    """Even semantically-aligned values are rejected — explicit is safer."""
    with pytest.raises(ValueError, match="cannot be combined"):
        # incremental=True (use cache) aligns with cleanScan=False (use cache),
        # but having both is still ambiguous payload state.
        _build_evaluation_options({"incremental": True, "cleanScan": False})
