"""Assistant tool registry and tool implementations."""
from quodeq.assistant.tools._actions import register_action_tools
from quodeq.assistant.tools._context import ToolContext
from quodeq.assistant.tools._overview import register_overview_tools
from quodeq.assistant.tools._read_tools import register_read_tools
from quodeq.assistant.tools._registry import ToolError, ToolRegistry, ToolSpec
from quodeq.assistant.tools._repo_tools import register_repo_tools

__all__ = ["ToolContext", "ToolError", "ToolRegistry", "ToolSpec", "build_registry"]


def build_registry(ctx: ToolContext) -> ToolRegistry:
    registry = ToolRegistry()
    register_read_tools(registry, ctx)
    register_overview_tools(registry, ctx)
    register_repo_tools(registry, ctx)
    register_action_tools(registry, ctx)
    return registry
