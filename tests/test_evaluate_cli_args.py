from codecompass.evaluate.lib.cli_parser import parse_cli_args


def test_parse_cli_args_dimensions():
    result = parse_cli_args(["-d", "a,b", "disc", "repo"])
    assert result.dimensions == ["a", "b"]



def test_parse_cli_args_evaluations_flag():
    result = parse_cli_args(["--evaluations", "/tmp/evaluations", "disc", "repo"])
    assert result.reports_dir == "/tmp/evaluations"
    assert result.reports_defaulted is False


def test_parse_cli_args_single_repo_defaults_discipline():
    result = parse_cli_args(["/repo/path"])
    assert result.repo == "/repo/path"
    assert result.discipline is None
