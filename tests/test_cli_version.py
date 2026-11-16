"""`quodeq --version` prints the version.

It used to fall through to the dashboard, whose parser rejected the flag and
printed its usage. argparse's version action exits while the top-level parser
runs, before any command is chosen.
"""
from __future__ import annotations

import pytest

import quodeq
from quodeq.cli_parser import build_parser


def test_version_flag_prints_the_version_and_exits(capsys):
    with pytest.raises(SystemExit) as stop:
        build_parser().parse_known_args(["--version"])
    assert stop.value.code == 0
    assert capsys.readouterr().out.strip() == f"quodeq {quodeq.__version__ or 'unknown'}"

