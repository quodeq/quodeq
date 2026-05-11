from pathlib import Path

import quodeq.resolver.languages  # noqa: F401  imported for side-effects
from quodeq.resolver.registry import get_adapter_for


def test_stub_adapter_registered_for_stub_extension():
    adapter = get_adapter_for(Path("/x.stub"))
    assert adapter.language == "stub"
    result = adapter.parse(b"")
    assert result.classes == []
    assert result.functions == []
