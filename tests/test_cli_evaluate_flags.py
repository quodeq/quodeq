from codecompass.cli import build_parser


def test_evaluate_flags():
    parser = build_parser()
    args = parser.parse_args(["evaluate", "-d", "sim", "-n", "discipline", "/tmp/repo"])

    assert args.command == "evaluate"
    assert args.dimensions == "sim"
    assert args.numerical is True
    assert args.discipline == "discipline"
    assert args.repo == "/tmp/repo"
