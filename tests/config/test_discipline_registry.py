from pathlib import Path

import pytest

from quodeq.config.discipline_registry import DisciplineRegistry
from quodeq.config.paths import default_paths


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
detect_file=package.json
detect_contains="react"
suggested_topics=React Best Practices,Frontend Architecture,TypeScript Standards
""".strip()
    )

    registry = DisciplineRegistry.from_file(conf)
    rule = registry.disciplines["frontend_react"]
    assert rule.detect_contains == ("react",)
    assert rule.suggested_topics == (
        "React Best Practices",
        "Frontend Architecture",
        "TypeScript Standards",
    )


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


def test_detect_file_without_contains_does_not_misalign_alts(tmp_path: Path):
    """A primary detect_file without detect_contains must not let later detect_file_alt entries
    bypass their detect_contains check via index misalignment.

    Regression: python_django had detect_file=manage.py (no contains), then
    detect_file_alt2=pyproject.toml + detect_contains_alt2=django. The parser dropped the
    leading None from detect_contains, shifting indices so pyproject.toml's check fell out of
    range and matched any pyproject.toml regardless of content.
    """
    conf = tmp_path / "disciplines.conf"
    conf.write_text(
        """
[python_django]
language=python
detect_file=manage.py
detect_file_alt=requirements.txt
detect_contains_alt=django
detect_file_alt2=pyproject.toml
detect_contains_alt2=django
detect_priority=4
""".strip()
    )

    repo = tmp_path / "repo"
    repo.mkdir()
    # pyproject.toml present but no "django" anywhere — should NOT match python_django.
    (repo / "pyproject.toml").write_text('[project]\nname = "quodeq"\ndependencies = ["flask"]\n')

    registry = DisciplineRegistry.from_file(conf)
    rule = registry.disciplines["python_django"]
    # Alignment invariant: contains tuple must align 1:1 with files tuple.
    assert len(rule.detect_contains) == len(rule.detect_files)
    assert rule.detect_contains[0] == ""  # manage.py has no content check
    assert rule.detect_contains[2] == "django"  # pyproject.toml must check for "django"

    matches = registry.detect_matches(repo)
    assert "python_django" not in matches


def test_validate_flags_unknown_keys(tmp_path: Path, capsys: pytest.CaptureFixture):
    conf = tmp_path / "disciplines.conf"
    conf.write_text(
        """
[python_django]
detect_file=manage.py
detect_contians=django
detect_priority=4
""".strip()
    )
    DisciplineRegistry.from_file(conf)
    assert "'detect_contians'" in capsys.readouterr().err


def test_validate_flags_dangling_excludes(tmp_path: Path, capsys: pytest.CaptureFixture):
    conf = tmp_path / "disciplines.conf"
    conf.write_text(
        """
[a]
detect_file=foo
detect_excludes=does_not_exist
""".strip()
    )
    DisciplineRegistry.from_file(conf)
    assert "does_not_exist" in capsys.readouterr().err


def test_validate_flags_rule_with_no_triggers(tmp_path: Path, capsys: pytest.CaptureFixture):
    conf = tmp_path / "disciplines.conf"
    conf.write_text("[a]\nlanguage=python\n")
    DisciplineRegistry.from_file(conf)
    assert "no triggers" in capsys.readouterr().err


def test_strict_mode_raises_on_validation_failure(tmp_path: Path):
    conf = tmp_path / "disciplines.conf"
    conf.write_text("[a]\ndetect_file=foo\ndetect_excludes=missing\n")
    with pytest.raises(ValueError, match="missing"):
        DisciplineRegistry.from_file(conf, strict=True)


def test_bundled_disciplines_conf_passes_strict_validation():
    """Regression guard: the shipped disciplines.conf must have no typos, no
    dangling detect_excludes, and no rules without triggers. If this fails,
    add a unit test for the new defect and fix the conf — don't loosen the gate."""
    conf = default_paths().disciplines_conf
    if not conf.exists():
        pytest.skip("disciplines.conf not installed")
    DisciplineRegistry.from_file(conf, strict=True)  # raises on any issue
