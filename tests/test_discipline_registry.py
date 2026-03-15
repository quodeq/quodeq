from pathlib import Path

from quodeq.config.discipline_registry import DisciplineRegistry


def test_registry_parses_disciplines(tmp_path: Path):
    conf = tmp_path / "disciplines.conf"
    conf.write_text(
        """
[frontend_react]
language=typescript
category=frontend
detect_file=package.json
detect_contains=react
detect_priority=6

[backend_springboot_java]
language=java
category=backend
detect_file=pom.xml
detect_contains=spring-boot
detect_priority=5
""".strip()
    )

    registry = DisciplineRegistry.from_file(conf)
    assert "frontend_react" in registry.disciplines
    assert registry.disciplines["frontend_react"].detect_files == ("package.json",)
    assert registry.disciplines["backend_springboot_java"].detect_priority == 5


def test_registry_parses_suggested_topics_and_quotes(tmp_path: Path):
    conf = tmp_path / "disciplines.conf"
    conf.write_text(
        """
[frontend_react]
detect_contains="react"
suggested_topics=React Best Practices,Frontend Architecture,TypeScript Standards
""".strip()
    )

    registry = DisciplineRegistry.from_file(conf)
    rule = registry.disciplines["frontend_react"]
    assert rule.detect_contains == ("react",)
    assert rule.suggested_topics == [
        "React Best Practices",
        "Frontend Architecture",
        "TypeScript Standards",
    ]


def test_registry_detects_by_file_contains(tmp_path: Path):
    conf = tmp_path / "disciplines.conf"
    conf.write_text(
        """
[frontend_react]
detect_file=package.json
detect_contains=react
detect_priority=6

[nodejs]
detect_file=package.json
detect_priority=9
detect_fallback=true
""".strip()
    )

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "package.json").write_text('{"dependencies": {"react": "^18.0.0"}}')

    registry = DisciplineRegistry.from_file(conf)
    matches = registry.detect_matches(repo)
    assert "frontend_react" in matches
    # nodejs has detect_fallback=true — excluded when a non-fallback matched
    assert "nodejs" not in matches


def test_choose_highest_priority(tmp_path: Path):
    conf = tmp_path / "disciplines.conf"
    conf.write_text(
        """
[a]
detect_priority=2

[b]
detect_priority=1
""".strip()
    )

    registry = DisciplineRegistry.from_file(conf)
    assert registry.choose_highest_priority(["a", "b"]) == "b"
