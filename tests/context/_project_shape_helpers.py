"""Manifest writer shared by the test_project_shape* siblings."""
from pathlib import Path


def _write(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
