"""Two project axes that both spell "local": where an assistant session's
data lives (ProjectSource) and where a project's code lives (ProjectLocation)."""
from __future__ import annotations

from quodeq.core.types.project_source import ProjectLocation, ProjectSource


def test_project_source_values():
    assert {m.name: m.value for m in ProjectSource} == {"LOCAL": "local", "SHARED": "shared"}


def test_project_location_values():
    assert {m.name: m.value for m in ProjectLocation} == {"LOCAL": "local", "ONLINE": "online"}


def test_the_axes_do_not_accept_each_others_words():
    assert "online" not in ProjectSource
    assert "shared" not in ProjectLocation
