"""list_builtin must skip malformed per-dimension entries, mirroring list_custom."""
from __future__ import annotations

from pathlib import Path

from quodeq.services._standards_queries import list_builtin


def test_list_builtin_skips_dimension_missing_id() -> None:
    """A dimension entry missing 'id' must be skipped, not raise, mirroring
    list_custom's try/except (OSError, ValueError, KeyError) guard."""
    dimensions_data = {
        "applies": [
            {"id": "security", "source": "OWASP"},
            {"source": "no id here"},  # malformed: missing required 'id'
            {"id": "performance", "source": "ISO"},
        ]
    }

    def fake_read_json(path: Path) -> dict:
        return dimensions_data

    result = list_builtin(
        dimensions_file=Path("/fake/dimensions.json"),
        compiled_dir=Path("/fake/compiled"),
        read_json=fake_read_json,
    )

    ids = [meta.id for meta in result]
    assert ids == ["security", "performance"]
