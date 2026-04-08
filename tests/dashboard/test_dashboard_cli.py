from quodeq.dashboard.cli import parse_args


def test_default_uses_native():
    config = parse_args([])
    assert config.build.use_native is True
    assert config.build.verbose is False


def test_browser_flag_disables_native():
    config = parse_args(["--browser"])
    assert config.build.use_native is False


def test_verbose_flag():
    config = parse_args(["--verbose"])
    assert config.build.verbose is True


def test_browser_and_verbose():
    config = parse_args(["--browser", "--verbose"])
    assert config.build.use_native is False
    assert config.build.verbose is True
