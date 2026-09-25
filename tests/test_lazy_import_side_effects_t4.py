"""Import-time state becomes lazy: no side effect on import, old names shim.

Values that used to be computed at import time -- SKIP_DIRS (a detection.json
read in analysis/_api_standards_text.py, re-exported eagerly by
analysis/subprocess.py) and the webview diagnostic log (mkdir + open in
dashboard/_webview_diag.py) -- are now ``functools.cache``-d accessors, with
the old module-level name reached through a ``__getattr__`` shim (PEP 562)
so ``from module import OLD_NAME`` still works. USE_COLOR's own shim/lazy
tests live in tests/shared/test_env_seams_t5.py, next to should_use_color.

Review Focus 3: importing any of these modules must have no side effect (no
file read, no mkdir, no open). Each side-effect test patches the filesystem
call to raise RuntimeError -- not OSError, which both loaders catch
internally as their production fallback path, so an OSError patch would
pass even if the call still ran eagerly at import.

analysis._api_standards_text and dashboard._webview_diag are private
modules with no public re-export of their lazy accessor (skip_dirs,
diag_stream) for a test to import directly without growing the
private-import-tests ratchet (tools/private_imports_tests_baseline.txt,
shrink-only). Both side-effect tests below spawn a fresh interpreter
(subprocess) that imports the private module directly instead -- this also
sidesteps a real gap in importlib.reload: reloading an already-cached
module only re-executes ITS OWN top level, not a dependency's, so
reload-testing the public re-exporter (analysis.subprocess) would silently
pass even with the eager read still in place, once _api_standards_text is
already cached from an earlier test in the session (verified: it does).
Only _api_standards_text itself is patch-tested for the read (subprocess.py
pulls in a much larger dependency tree -- jsonschema included -- that does
its own legitimate file reads at import, which a blanket Path.read_text
patch can't tell apart from the one this task cares about); subprocess.py's
shim is instead pinned by value equality below.
"""
from __future__ import annotations

import subprocess
import sys


def _run_fresh_interpreter(script: str) -> subprocess.CompletedProcess:
    """Run *script* in a brand-new interpreter -- a genuinely fresh import,
    unlike importlib.reload (see module docstring)."""
    return subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False,
    )


class TestSkipDirsLazyImport:
    """SKIP_DIRS: skip_dirs() with functools.cache, read once."""

    def test_importing_api_standards_text_does_not_read_detection_json(self):
        script = (
            "import quodeq  # let package init read its own metadata before Path is patched\n"
            "from pathlib import Path\n"
            "def _boom(self, *a, **k):\n"
            "    raise RuntimeError('detection.json must not be read at import time')\n"
            "Path.read_text = _boom\n"
            "import quodeq.analysis._api_standards_text\n"  # must not raise
            "print('OK')\n"
        )
        result = _run_fresh_interpreter(script)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "OK" in result.stdout

    def test_skip_dirs_old_name_matches_the_function_through_the_shim(self):
        script = (
            "from quodeq.analysis._api_standards_text import SKIP_DIRS, skip_dirs\n"
            "assert SKIP_DIRS == skip_dirs(), (SKIP_DIRS, skip_dirs())\n"
            "from quodeq.analysis.subprocess import SKIP_DIRS as via_subprocess\n"
            "assert via_subprocess == skip_dirs(), (via_subprocess, skip_dirs())\n"
            "print('OK')\n"
        )
        result = _run_fresh_interpreter(script)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "OK" in result.stdout


class TestDiagStreamLazyImport:
    """webview diag log: diag_stream() with functools.cache does the mkdir
    and open on first call, not at import."""

    def test_importing_webview_diag_does_not_touch_the_filesystem(self):
        script = (
            "import quodeq  # let package init read its own metadata before Path is patched\n"
            "from pathlib import Path\n"
            "def _boom(self, *a, **k):\n"
            "    raise RuntimeError('diag log must not touch the filesystem at import time')\n"
            "Path.mkdir = _boom\n"
            "Path.open = _boom\n"
            "import quodeq.dashboard._webview_diag\n"  # must not raise
            "print('OK')\n"
        )
        result = _run_fresh_interpreter(script)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "OK" in result.stdout

    def test_diag_old_name_matches_diag_stream(self):
        script = (
            "import quodeq.dashboard._webview_diag as mod\n"
            "assert mod.diag is mod.diag_stream(), (mod.diag, mod.diag_stream())\n"
            "print('OK')\n"
        )
        result = _run_fresh_interpreter(script)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "OK" in result.stdout
