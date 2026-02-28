from codecompass.evaluate.cli import build_parser


def test_evaluate_help_includes_subcommand():
    parser = build_parser()
    help_text = parser.format_help()
    assert "evaluate" in help_text
