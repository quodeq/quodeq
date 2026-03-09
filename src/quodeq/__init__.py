from quodeq.action_provider import ActionProvider


def main() -> None:
    from quodeq.cli import main as cli_main

    raise SystemExit(cli_main())
