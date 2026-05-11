from pathlib import Path

import quodeq.resolver.languages  # noqa: F401  imported for side-effects
from quodeq.resolver.registry import get_adapter_for


def test_python_adapter_auto_registered():
    adapter = get_adapter_for(Path("/some/file.py"))
    assert adapter.language == "python"
