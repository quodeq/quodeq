"""Ensure the tools/ directory is importable for tool tests."""
import sys
from pathlib import Path

_tools_dir = str(Path(__file__).resolve().parents[2] / "tools")
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)
