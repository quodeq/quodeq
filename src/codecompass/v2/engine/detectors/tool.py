from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from codecompass.v2.engine.detectors.base import DetectorBase
from codecompass.v2.engine.finding import Finding

# Parser registry: tool_name → callable(stdout, config) -> list[Finding]
_PARSER_REGISTRY: dict[str, Callable] = {}


def register_parser(tool_name: str, parser: Callable) -> None:
    """Register a parser function for a tool name."""
    _PARSER_REGISTRY[tool_name] = parser


class ToolDetector(DetectorBase):
    """Runs an external tool command and passes output to a registered parser."""

    def run(self, src: Path, config: dict) -> list[Finding]:
        tool_name = config.get("tool", "")
        command_template = config.get("command", "")
        optional = config.get("optional", False)
        timeout = config.get("timeout", 60)

        parser = _PARSER_REGISTRY.get(tool_name)
        if not parser:
            if optional:
                return []
            raise ValueError(f"No parser registered for tool: {tool_name}")

        command = command_template.replace("{src}", str(src))

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            # Many tools use non-zero exit for "found issues" — still parse stdout
            return parser(result.stdout, config)
        except subprocess.TimeoutExpired:
            return []
        except OSError:
            if optional:
                return []
            raise
