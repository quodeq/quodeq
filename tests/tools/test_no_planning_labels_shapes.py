"""Unit tests for the planning-label gate's scanners and shapes.

Split out of test_no_planning_labels.py (which stayed at the file-size
ceiling) so the shape catalog can grow without crowding the gate itself.
Every shape in SHAPES has a positive and a negative case here.
"""
from __future__ import annotations

import re

import pytest

from tests.tools.test_no_planning_labels import REPO, _iter_sources, js_prose, labels_in, python_prose


def test_python_prose_reads_comments_and_docstrings_only():
    prose = python_prose(
        '"""Module doc."""\n'
        "# a comment\n"
        "X = 'a value'\n"
        "def f():\n"
        "    '''Function doc.'''\n"
        "    return 'another value'\n"
        "rows = (\n"
        "    'VALUES (1)'\n"
        ")\n"
    )
    assert [text for _, text in prose] == [
        '"""Module doc."""', "# a comment", "'''Function doc.'''",
    ]


def test_js_prose_ignores_slashes_inside_strings():
    prose = js_prose(
        "const url = 'https://example.com'; // trailing\n"
        "/* block\n   continues */\n"
        "const t = `a // b`;\n"
    )
    assert [(lineno, text.strip()) for lineno, text in prose] == [
        (1, "// trailing"),
        (2, "/* block\n   continues */"),
    ]


def test_js_scanner_finds_every_comment_line():
    """Self-check: a line opening `//`, `/*` or `{/*` (JSX) must fall inside
    some span `js_prose` returns, or something earlier confused the scanner
    (usually a template literal's `${...}` or a regex literal) into reading
    past it.
    """
    comment_open = re.compile(r"^\s*(//|/\*|\{/\*)")
    missed = []
    for path in _iter_sources():
        if path.suffix == ".py":
            continue
        source = path.read_text(encoding="utf-8")
        covered = set()
        for lineno, text in js_prose(source):
            for offset in range(text.count("\n") + 1):
                covered.add(lineno + offset)
        for i, line in enumerate(source.splitlines(), start=1):
            if comment_open.match(line) and i not in covered:
                missed.append(f"{path.relative_to(REPO)}:{i}: {line.strip()[:80]}")
    assert missed == [], "js_prose missed comment lines:\n" + "\n".join(missed)


@pytest.mark.parametrize("text, expected", [
    ("Task 4 follow-up", ["Task 4"]),
    ("pins the Task 3.5 contract", ["Task 3.5"]),
    ("Plan B precedence", ["Plan B"]),
    ("pre-Plan-A runs", ["Plan-A"]),
    ("Plan 1 naming note", ["Plan 1"]),
    ("Cluster 12, Cluster36", ["Cluster 12", "Cluster36"]),
    ("added in cluster 25", ["cluster 25"]),
    ("until the Phase 2 action registry", ["Phase 2"]),
    ("landed in Wave 3", ["Wave 3"]),
    ("the route serializes (WS6)", ["WS6"]),
    ("// P4-T2: Violations never received", ["P4-T2"]),
    ("// P6: the Overview never dims", ["P6"]),
    ("Finding 1 (P5 final review)", ["P5"]),
    ("Split out (B4/B5e)", ["B4", "B5e"]),
    ("Post-V2 (B6.2c): gone", ["Post-V2", "B6.2c"]),
    ("misattributed -- audit finding C1", ["audit finding C1"]),
    ("Review findings 3 & 4", ["Review findings 3"]),
    ("Audit A2: a list that never loads", ["Audit A2"]),
    ("reused (finding 5398)", ["finding 5398"]),
    ("observed: run 838d807e", ["run 838d807e"]),
    ("(fix round 1, a11y)", ["fix round"]),
    ("final whole-branch review", ["whole-branch review"]),
    ("Critical 1 (belt-and-braces)", ["Critical 1"]),
    ("after the post-PR review (M8)", ["review (M8"]),
    ("task 6 sweep", ["task 6"]),
    ("TASK 12 revisited", ["TASK 12"]),
    ("Run fa56db32e1 rated it critical", ["Run fa56db32e1"]),
    ("observed in run abcdef0123 too", ["run abcdef0123"]),
    ("ten findings 5926 outstanding", ["findings 5926"]),
    ("review findings d3 & 4", ["review findings d3"]),
    ("usability cycle 1, task 6 sweep", ["usability cycle 1", "task 6"]),
    ("fault-tolerance cycle 1 fix wave", ["fault-tolerance cycle 1"]),
    ("clean-architecture cycle 2 follow-up", ["clean-architecture cycle 2"]),
    ("final review item B found it", ["review item B"]),
])
def test_label_shape_matches(text, expected):
    assert labels_in(text) == expected


@pytest.mark.parametrize("text", [
    "tasks 4, planning, clustered",
    "a Plan for the week",
    "Phase 1: radial gradient background",
    "orbiting particles (part of phase 3)",
    "# Only P2 should appear, P1 has none",
    "Security/P1: critical violation",
    "class key is (security, P1, a.py)",
    "a B2B deal",
    "found in 42 files, finding 12",
    "the run 12ab finished",
    "the M8 model weights",
    "V2 cache owns incremental state",
    "the Critical path",
    "review findings are listed",
    "an audit of the store",
    "the task 's done",
    "a run of",
    "findings are",
    "the cycle",
    "item A in the list",
])
def test_label_shape_ignores_legitimate_text(text):
    assert labels_in(text) == []
