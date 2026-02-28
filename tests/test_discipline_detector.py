from pathlib import Path
import json

from codecompass.evaluate.lib.discipline_detector import (
    detect_discipline,
    detect_from_rules,
)


def test_detect_discipline_from_manifest(tmp_path: Path):
    manifest = tmp_path / ".codecompass.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "project": {"name": "demo"},
                "targets": [
                    {
                        "name": "demo",
                        "path": ".",
                        "discipline": "frontend_react",
                        "dimensions": "all",
                    }
                ],
            }
        )
    )

    detected = detect_discipline(str(tmp_path))
    assert detected == "frontend_react"


def test_detect_discipline_from_rules_uses_default_registry(tmp_path: Path):
    (tmp_path / "package.json").write_text("{}")
    detected = detect_from_rules(str(tmp_path))
    assert detected == "nodejs"
