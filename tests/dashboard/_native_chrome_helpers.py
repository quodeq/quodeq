"""Shared markers for tests/dashboard/test_native_chrome*.py siblings."""
import sys

import pytest


# Some tests import PyObjCTools to patch AppHelper. pyobjc is darwin-only
# (pywebview pulls it in under sys_platform == 'darwin'), so those tests can
# only run on macOS — they would ModuleNotFoundError on Linux/Windows CI.
_MACOS_ONLY = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="exercises macOS AppKit/PyObjC native chrome; pyobjc is darwin-only",
)
