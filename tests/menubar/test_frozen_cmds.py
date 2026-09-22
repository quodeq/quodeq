"""Frozen/dev subprocess commands for the menu bar and its dashboard launches."""
from __future__ import annotations

import sys
from unittest.mock import patch

from quodeq.shared import frozen as _frozen


def test_subprocess_cmd_menubar_dev():
    with patch.object(sys, "frozen", False, create=True):
        assert _frozen.subprocess_cmd("menubar") == [
            sys.executable, "-m", "quodeq.menubar",
        ]


def test_subprocess_cmd_menubar_frozen():
    with patch.object(sys, "frozen", True, create=True):
        assert _frozen.subprocess_cmd("menubar") == [sys.executable, "--_menubar"]


def test_dashboard_cmd_dev():
    with patch.object(sys, "frozen", False, create=True):
        assert _frozen.dashboard_cmd(["--no-open", "--port", "7863"]) == [
            sys.executable, "-m", "quodeq.dashboard", "--no-open", "--port", "7863",
        ]


def test_dashboard_cmd_frozen():
    with patch.object(sys, "frozen", True, create=True):
        assert _frozen.dashboard_cmd(["--no-open"]) == [sys.executable, "--no-open"]


def test_dashboard_cmd_no_args():
    with patch.object(sys, "frozen", True, create=True):
        assert _frozen.dashboard_cmd() == [sys.executable]
