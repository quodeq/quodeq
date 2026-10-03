"""Assistant tool registry and tool implementations."""
from quodeq.assistant.tools.actions import ActionContext, register_action_tools
from quodeq.assistant.tools._context import ToolContext
from quodeq.assistant.tools._context_tool import register_context_tool
from quodeq.assistant.tools._overview import register_overview_tools
from quodeq.assistant.tools._read_tools import register_read_tools
from quodeq.assistant.tools._read_tools_common import default_findings_repo_factory
from quodeq.assistant.tools.registry import ToolError, ToolRegistry, ToolSpec
from quodeq.assistant.tools._repo_tools import register_repo_tools
from quodeq.assistant.tools._web_tools import register_web_tools

__all__ = ["ActionContext", "ToolContext", "ToolError", "ToolRegistry", "ToolSpec",
           "build_registry", "default_findings_repo_factory", "register_web_tools"]


def build_registry(ctx: ToolContext) -> ToolRegistry:
    """Assemble the tool registry for one session.

    Read-only sessions get no ``draft_action``, so a shared session has no
    mutation primitive to gate further down.
    """
    registry = ToolRegistry()
    register_context_tool(registry, ctx)
    register_read_tools(registry, ctx)
    register_overview_tools(registry, ctx)
    register_repo_tools(registry, ctx)
    # Read-only (shared) sessions get NO mutation primitive: draft_action is
    # absent from the registry, so there is nothing to gate downstream.
    if not ctx.read_only:
        register_action_tools(registry, ctx)
    return registry
