from codecompass.cli import build_parser


def test_evaluate_v1_flags():
    parser = build_parser()
    args = parser.parse_args(["evaluate-v1", "-d", "sim", "-n", "discipline", "/tmp/repo"])

    assert args.command == "evaluate-v1"
    assert args.dimensions == "sim"
    assert args.numerical is True
    assert args.discipline == "discipline"
    assert args.repo == "/tmp/repo"


def test_evaluate_v2_flags():
    parser = build_parser()
    args = parser.parse_args(["evaluate", "/tmp/repo", "-p", "python", "-m", "grades"])

    assert args.command == "evaluate"
    assert args.repo == "/tmp/repo"
    assert args.plugin == "python"
    assert args.mode == "grades"
    assert args.output == "evaluations"
    assert args.no_prescan is False
    assert args.evidence_only is False
