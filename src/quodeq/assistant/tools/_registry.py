"""Provider-agnostic tool registry: one implementation, MCP + function-calling exposure."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

_logger = logging.getLogger(__name__)


class ToolError(Exception):
    """User-facing tool failure (bad input, missing context)."""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., dict]


class ToolRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"duplicate tool: {spec.name}")
        self._specs[spec.name] = spec

    def names(self) -> list[str]:
        return sorted(self._specs)

    def openai_tools(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": s.name,
                    "description": s.description,
                    "parameters": s.parameters,
                },
            }
            for s in self._specs.values()
        ]

    def dispatch(self, name: str, arguments: dict[str, Any]) -> dict:
        spec = self._specs.get(name)
        if spec is None:
            return {"ok": False, "error": f"unknown tool: {name}"}
        try:
            return {"ok": True, "result": spec.handler(**arguments)}
        except ToolError as exc:
            return {"ok": False, "error": str(exc)}
        except TypeError as exc:
            return {"ok": False, "error": f"invalid arguments for {name}: {exc}"}
        except Exception:  # noqa: BLE001 - a tool bug must not kill the turn
            _logger.exception("tool %s crashed", name)
            return {"ok": False, "error": f"tool {name} failed internally"}
