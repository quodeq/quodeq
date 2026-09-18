"""Unit tests for the pom.xml and Gradle manifest parsers."""
from __future__ import annotations

import pytest

from quodeq.config._dependency_parsers import has_gradle_dependency, has_pom_xml_dependency


# --- pom.xml -----------------------------------------------------------------




@pytest.mark.parametrize("body, needle, expected", [
    # spring-boot artifactId substring match.
    (
        "<project>"
        "<dependencies><dependency>"
        "<groupId>org.springframework.boot</groupId>"
        "<artifactId>spring-boot-starter-web</artifactId>"
        "</dependency></dependencies></project>",
        "spring-boot", True,
    ),
    # io.quarkus exact groupId.
    (
        "<project>"
        "<dependencies><dependency>"
        "<groupId>io.quarkus</groupId>"
        "<artifactId>quarkus-resteasy</artifactId>"
        "</dependency></dependencies></project>",
        "io.quarkus", True,
    ),
    # Description text must NOT match (chunk-9 regression).
    (
        "<project>"
        "<description>migrating off spring-boot to quarkus</description>"
        "<dependencies><dependency>"
        "<groupId>io.quarkus</groupId>"
        "<artifactId>quarkus-resteasy</artifactId>"
        "</dependency></dependencies></project>",
        "spring-boot", False,
    ),
    # Maven default namespace is stripped.
    (
        '<project xmlns="http://maven.apache.org/POM/4.0.0">'
        "<dependencies><dependency>"
        "<groupId>org.springframework.boot</groupId>"
        "<artifactId>spring-boot-starter</artifactId>"
        "</dependency></dependencies></project>",
        "spring-boot", True,
    ),
    # Empty content → no match.
    ("not <xml", "anything", False),
])
def test_pom_xml(body: str, needle: str, expected: bool) -> None:
    assert has_pom_xml_dependency(body, needle) is expected


def test_pom_xml_entity_expansion_attack_rejected() -> None:
    """Crafted billion-laughs / XXE payload is safely rejected."""
    # Billion-laughs style payload: nested entity expansion.
    payload = (
        '<?xml version="1.0"?>'
        '<!DOCTYPE project ['
        '<!ENTITY lol "lol">'
        '<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
        '<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">'
        ']>'
        '<project>'
        '<description>&lol3;</description>'
        '</project>'
    )
    # Guard should reject DOCTYPE, returning empty set (no dependencies matched).
    assert has_pom_xml_dependency(payload, "anything") is False


def test_pom_xml_normal_without_doctype_parses() -> None:
    """Normal pom.xml without DOCTYPE should parse correctly (no false-positive rejection)."""
    normal_pom = (
        '<?xml version="1.0"?>'
        '<project>'
        '<dependencies><dependency>'
        '<groupId>org.springframework.boot</groupId>'
        '<artifactId>spring-boot-starter-web</artifactId>'
        '</dependency></dependencies>'
        '</project>'
    )
    # Should find spring-boot dependency normally.
    assert has_pom_xml_dependency(normal_pom, "spring-boot") is True
    assert has_pom_xml_dependency(normal_pom, "nonexistent") is False


# --- Gradle (Groovy / Kotlin DSL) -------------------------------------------


@pytest.mark.parametrize("body, needle, expected", [
    # Groovy DSL.
    ('implementation "org.springframework.boot:spring-boot-starter-web:3.2.0"', "spring-boot", True),
    # Kotlin DSL.
    ('implementation("io.ktor:ktor-server-core:2.3.0")', "io.ktor", True),
    # Plugins block.
    ('plugins { id "org.springframework.boot" version "3.2.0" }', "org.springframework.boot", True),
    # // line comment must NOT match.
    ('// migrating off org.springframework.boot\nplugins { id "kotlin" }', "org.springframework.boot", False),
    # /* block comment */ must NOT match.
    (
        '/* fall-back: io.ktor used to be here */\nplugins { id "kotlin" }',
        "io.ktor", False,
    ),
    # Mixed: comment FP-bait + real dep — should still match the real dep.
    (
        '// notes about io.ktor\nimplementation("io.ktor:ktor-server-core:2.3.0")',
        "io.ktor", True,
    ),
])
def test_gradle(body: str, needle: str, expected: bool) -> None:
    assert has_gradle_dependency(body, needle) is expected
