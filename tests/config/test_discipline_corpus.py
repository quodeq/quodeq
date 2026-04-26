"""Acceptance corpus for discipline detection.

Each fixture under ``tests/fixtures/discipline_corpus/<name>/`` has two parts:

* ``repo/`` — a minimal synthetic codebase that exercises one detection path.
* ``expected.json`` — what the live ``disciplines.conf`` should produce for it.

The test runs the bundled ``disciplines.conf`` against every fixture and asserts
the classification, language, and suggested topics. Adding a fixture is the only
thing required to add coverage for a new stack — no test code changes.

``expected.json`` keys
----------------------

* ``matches`` (list[str], required): the set of disciplines that must fire,
  order-insensitive.
* ``primary`` (str, optional): name of the rule expected to win priority order.
  When set, ``language`` and ``topics`` apply to this rule.
* ``language`` (str, optional): expected ``language`` field on ``primary``.
* ``topics`` (list[str], optional): expected ``suggested_topics`` on ``primary``.
* ``not_matches`` (list[str], optional): rules that must NOT fire (regression
  guard for false positives, e.g. quodeq classifying as Django).
* ``recursive`` (bool, optional): when true, run ``detect_matches_recursive``
  and aggregate matches across all subproject roots. Use this for monorepo
  fixtures where the project of interest lives in a subdirectory.
* ``xfail`` (str, optional): reason marker for a fixture that documents a known
  bug we have not fixed yet. The test still runs; failures become xfails so the
  corpus stays green while the gap is tracked.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.config.discipline_registry import DisciplineRegistry
from quodeq.config.paths import default_paths

CORPUS_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "discipline_corpus"


def _discover_fixtures() -> list[tuple[str, Path]]:
    if not CORPUS_ROOT.is_dir():
        return []
    fixtures: list[tuple[str, Path]] = []
    for entry in sorted(CORPUS_ROOT.iterdir()):
        if not entry.is_dir():
            continue
        if not (entry / "expected.json").is_file():
            continue
        if not (entry / "repo").is_dir():
            continue
        fixtures.append((entry.name, entry))
    return fixtures


@pytest.fixture(scope="module")
def registry() -> DisciplineRegistry:
    conf = default_paths().disciplines_conf
    if not conf.exists():
        pytest.skip("disciplines.conf not installed")
    return DisciplineRegistry.from_file(conf)


@pytest.mark.parametrize(
    ("name", "fixture_dir"),
    _discover_fixtures(),
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_discipline_corpus(
    name: str, fixture_dir: Path, registry: DisciplineRegistry, request: pytest.FixtureRequest,
) -> None:
    expected = json.loads((fixture_dir / "expected.json").read_text())
    if "xfail" in expected:
        request.applymarker(pytest.mark.xfail(reason=expected["xfail"], strict=False))

    repo = fixture_dir / "repo"
    if expected.get("recursive"):
        sub_results = registry.detect_matches_recursive(repo)
        actual: set[str] = set()
        for _path, sub_matches in sub_results:
            actual.update(sub_matches)
    else:
        actual = set(registry.detect_matches(repo))

    expected_matches = set(expected.get("matches", []))
    assert actual == expected_matches, (
        f"[{name}] match mismatch: expected {sorted(expected_matches)}, got {sorted(actual)}"
    )

    for forbidden in expected.get("not_matches", []):
        assert forbidden not in actual, f"[{name}] {forbidden!r} should not match but did"

    primary = expected.get("primary")
    if primary is not None:
        assert primary in registry.disciplines, f"[{name}] primary {primary!r} not in registry"
        rule = registry.disciplines[primary]
        if "language" in expected:
            assert rule.language == expected["language"], (
                f"[{name}] language mismatch on {primary!r}: "
                f"expected {expected['language']!r}, got {rule.language!r}"
            )
        if "topics" in expected:
            actual_topics = list(rule.suggested_topics or ())
            assert actual_topics == expected["topics"], (
                f"[{name}] topics mismatch on {primary!r}:\n"
                f"  expected {expected['topics']}\n  got      {actual_topics}"
            )


def test_corpus_has_fixtures() -> None:
    """Guardrail: catch a misconfigured fixtures dir before silently passing zero cases."""
    fixtures = _discover_fixtures()
    assert fixtures, f"no fixtures discovered under {CORPUS_ROOT}"
