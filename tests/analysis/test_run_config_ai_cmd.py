"""RunConfig.ai_cmd resolves through DispatchPolicy, not os.environ directly."""
from __future__ import annotations

from pathlib import Path

from quodeq.analysis._types import RunConfig
from quodeq.analysis.dispatch_policy import DispatchPolicy


def test_ai_cmd_uses_explicit_dispatch_policy():
    config = RunConfig(
        src=Path("."),
        language="python",
        dispatch=DispatchPolicy(
            provider_configs={}, ai_cmd="ollama", file_size_cap=1000,
        ),
    )
    assert config.ai_cmd == "ollama"
