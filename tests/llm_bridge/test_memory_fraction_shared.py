"""llamacpp and omlx's VRAM-per-context fallback (used when the backend
reports no real size/VRAM data) both estimate from the same fraction of
detected host memory. The value lives once on _ollama.py -- the module both
bridges already import _detect_memory/estimate_max_agents from -- and each
imports DEFAULT_MEMORY_FRACTION rather than retyping 0.5."""
from __future__ import annotations

from quodeq.llm_bridge._ollama import DEFAULT_MEMORY_FRACTION


def test_default_memory_fraction_is_one_half():
    assert DEFAULT_MEMORY_FRACTION == 0.5


def test_llamacpp_imports_the_shared_fraction():
    from quodeq.llm_bridge import _llamacpp

    assert _llamacpp.DEFAULT_MEMORY_FRACTION is DEFAULT_MEMORY_FRACTION


def test_omlx_imports_the_shared_fraction():
    from quodeq.llm_bridge import omlx

    assert omlx.DEFAULT_MEMORY_FRACTION is DEFAULT_MEMORY_FRACTION
