"""Unit tests for the layer-rule mechanics in tools/check_imports.py."""
from __future__ import annotations

import check_imports


def test_shared_is_a_checked_layer():
    assert "shared" in check_imports.LAYER_RULES
    # Only core (innermost) is allowed: shared re-exports a few pure helpers
    # whose real home is core/utils/io.py. Dependencies point inward.
    assert check_imports.LAYER_RULES["shared"] == {"core"}


def test_core_and_shared_are_strict():
    assert check_imports.STRICT_LAYERS == {"core", "shared"}


def test_strict_layer_denies_cross_cutting(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text("from quodeq.shared.utils import read_json\n", encoding="utf-8")
    violations = check_imports.check_file(f, "core")
    assert [(lineno, target) for lineno, target, _line in violations] == [(1, "shared")]


def test_strict_shared_denies_analysis_and_data(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text(
        "from quodeq.analysis._provider_cache import get_provider_configs\n"
        "import quodeq.data\n",
        encoding="utf-8",
    )
    violations = check_imports.check_file(f, "shared")
    assert [target for _lineno, target, _line in violations] == ["analysis", "data"]


def test_non_strict_layer_still_allows_shared(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text("from quodeq.shared.utils import read_json\n", encoding="utf-8")
    assert check_imports.check_file(f, "services") == []


def test_shared_may_import_itself(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text("from quodeq.shared.constants import DEFAULT_TIMEOUT\n", encoding="utf-8")
    assert check_imports.check_file(f, "shared") == []


def test_llm_bridge_is_a_leaf_layer():
    assert check_imports.LAYER_RULES["llm_bridge"] == set()


def test_ci_layer_rule():
    assert check_imports.LAYER_RULES["ci"] == {"core", "services", "analysis", "context"}


def test_llm_bridge_may_import_shared_but_not_services(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text(
        "from quodeq.shared.utils import read_json\n"
        "from quodeq.services.jobs import start_job\n",
        encoding="utf-8",
    )
    violations = check_imports.check_file(f, "llm_bridge")
    assert [target for _lineno, target, _line in violations] == ["services"]
