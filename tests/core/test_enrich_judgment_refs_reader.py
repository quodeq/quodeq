"""enrich_judgment resolves compiled refs only through the injected reader.

Core performs no file I/O itself (the ``RefsReader`` seam mirrors
``ReqMapReader``): with ``compiled_dir`` set but no reader, no refs are
attached; with a fake reader, the judgment is enriched from its output.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.core.evidence._refs import enrich_judgment
from quodeq.core.events.models import Judgment


def _judgment() -> Judgment:
    return Judgment(
        practice_id="S-CON-1", verdict="violation", dimension="security",
        file="app.py", line=3, reason="hardcoded secret", req="S-CON-1",
    )


class TestEnrichJudgmentRefsReader:
    def test_without_reader_attaches_no_refs(self) -> None:
        cache: dict[str, dict[str, list[dict]]] = {}

        enriched = enrich_judgment(
            _judgment(), ["CISQ-1"], Path("/does/not/matter"), cache,
        )

        assert enriched.req_refs == []
        assert cache == {"security": {}}

    def test_fake_reader_enriches_from_its_output(self) -> None:
        calls: list[tuple[str, str]] = []

        def fake_reader(compiled_dir: str, dimension: str) -> dict[str, list[dict]]:
            calls.append((compiled_dir, dimension))
            return {"S-CON-1": [{"label": "CISQ-1", "url": "https://example.com/1"}]}

        cache: dict[str, dict[str, list[dict]]] = {}
        compiled_dir = Path("/compiled")
        enriched = enrich_judgment(
            _judgment(), ["CISQ-1"], compiled_dir, cache,
            refs_reader=fake_reader,
        )

        assert calls == [(str(compiled_dir), "security")]
        assert [(r.label, r.url) for r in enriched.req_refs] == [
            ("CISQ-1", "https://example.com/1"),
        ]

    def test_reader_is_called_once_per_dimension(self) -> None:
        calls: list[str] = []

        def fake_reader(compiled_dir: str, dimension: str) -> dict[str, list[dict]]:
            calls.append(dimension)
            return {}

        cache: dict[str, dict[str, list[dict]]] = {}
        enrich_judgment(_judgment(), ["CWE-1"], Path("/compiled"), cache,
                        refs_reader=fake_reader)
        enrich_judgment(_judgment(), ["CWE-1"], Path("/compiled"), cache,
                        refs_reader=fake_reader)

        assert calls == ["security"]
