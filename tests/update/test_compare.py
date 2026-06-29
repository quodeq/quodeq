from quodeq.update.compare import is_newer, normalize


def test_normalize_strips_v_prefix() -> None:
    assert normalize("v1.5.0") == "1.5.0"
    assert normalize("1.5.0") == "1.5.0"
    assert normalize("  V2.0.0 ") == "2.0.0"


def test_is_newer_true_when_latest_greater() -> None:
    assert is_newer("1.4.0", "1.5.0") is True
    assert is_newer("1.4.0", "v1.4.1") is True


def test_is_newer_false_when_equal_or_older() -> None:
    assert is_newer("1.5.0", "1.5.0") is False
    assert is_newer("1.5.0", "1.4.0") is False


def test_is_newer_ignores_prereleases() -> None:
    # A pre-release of a higher version must NOT count as newer.
    assert is_newer("1.4.0", "1.5.0rc1") is False


def test_is_newer_handles_missing_or_garbage() -> None:
    assert is_newer(None, "1.5.0") is False
    assert is_newer("1.4.0", None) is False
    assert is_newer("1.4.0", "not-a-version") is False
