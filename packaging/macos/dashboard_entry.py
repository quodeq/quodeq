"""PyInstaller entry point for the Quodeq Dashboard.

Dispatches internal subprocess flags before falling through to the
normal dashboard CLI.  Flags use a leading underscore to signal they
are private / not user-facing.
"""
import os
import sys

# Stdio MCP servers (quodeq.shared.frozen.MCP_FINDINGS / MCP_ASSISTANT). An
# agent CLI spawns them and speaks JSON-RPC over their stdin and stdout.
_MCP_FINDINGS_FLAG = "--_mcp_findings"
_MCP_ASSISTANT_FLAG = "--_mcp_assistant"
_MCP_FLAGS = (_MCP_FINDINGS_FLAG, _MCP_ASSISTANT_FLAG)


def _setup_frozen_env() -> None:
    """Set environment variables for frozen mode."""
    base = sys._MEIPASS  # type: ignore[attr-defined]
    os.environ.setdefault("QUODEQ_STATIC_DIST", os.path.join(base, "quodeq", "static"))


def main() -> int:
    flag = sys.argv[1] if len(sys.argv) > 1 else ""
    if getattr(sys, "frozen", False):
        _setup_frozen_env()
        # Load user's shell PATH so CLI tools (claude, node, etc.) are found.
        # Not for the MCP servers: the login shell would share their JSON-RPC
        # stdin and delay the handshake, and they inherit the PATH of the app
        # that started the CLI.
        if flag not in _MCP_FLAGS:
            from quodeq.dashboard._frozen import source_user_path
            source_user_path()

    # Internal subprocess dispatch — checked before heavy imports.
    if flag:
        if flag == "--_api":
            from quodeq.api.app import main as api_main
            api_main()
            return 0

        if flag == "--_webview":
            # Rewrite argv so _webview_window.main() sees [prog, url, sock, pid]
            sys.argv = [sys.argv[0]] + sys.argv[2:]
            from quodeq.dashboard._webview_window import main as webview_main
            webview_main()
            return 0

        if flag == "--_menubar":
            from quodeq.menubar.app import main as menubar_main
            menubar_main()
            return 0

        if flag == "--_evaluate":
            # Rewrite argv so the CLI sees [prog, "evaluate", ...args]
            sys.argv = [sys.argv[0]] + sys.argv[2:]
            from quodeq.cli import main as cli_main
            return cli_main()

        if flag == _MCP_FINDINGS_FLAG:
            # Rewrite argv so the server sees [prog, findings_file, ...flags]
            sys.argv = [sys.argv[0]] + sys.argv[2:]
            from quodeq.analysis.mcp.findings_server import main as findings_main
            findings_main()
            return 0

        if flag == _MCP_ASSISTANT_FLAG:
            # Rewrite argv so the server sees [prog, ...flags]
            sys.argv = [sys.argv[0]] + sys.argv[2:]
            from quodeq.assistant.mcp.server import main as assistant_main
            assistant_main()
            return 0

    # Normal dashboard launch — force --no-build in frozen mode
    argv = None
    if getattr(sys, "frozen", False):
        raw = sys.argv[1:]
        if "--no-build" not in raw:
            raw.append("--no-build")
        argv = raw

    from quodeq.dashboard.cli import main as dashboard_main
    return dashboard_main(argv)


if __name__ == "__main__":
    sys.exit(main())
