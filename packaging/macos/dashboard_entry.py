"""PyInstaller entry point for the Quodeq Dashboard.

Dispatches internal subprocess flags before falling through to the
normal dashboard CLI.  Flags use a leading underscore to signal they
are private / not user-facing.
"""
import os
import sys


def _setup_frozen_env() -> None:
    """Set environment variables for frozen mode."""
    base = sys._MEIPASS  # type: ignore[attr-defined]
    os.environ.setdefault("QUODEQ_STATIC_DIST", os.path.join(base, "quodeq", "static"))


def main() -> int:
    if getattr(sys, "frozen", False):
        _setup_frozen_env()
        # Load user's shell PATH so CLI tools (claude, node, etc.) are found
        from quodeq.dashboard._frozen import source_user_path
        source_user_path()

    # Internal subprocess dispatch — checked before heavy imports.
    if len(sys.argv) > 1:
        flag = sys.argv[1]

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
