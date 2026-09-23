"""Gate: no planning or audit labels in the prose of src/quodeq and tests.

`Task 4`, `Plan B`, `Cluster 12`, `B6.2b`, `audit finding C1` or
`run 838d807e` are coordinates in a plan, an audit or a log that the next
reader cannot look up, so the sentence they appear in loses whatever reason
it was meant to carry. The fix is never to delete the sentence, it is to say
the reason in prose (or link the repo issue, which still resolves).

Scoped to comment and docstring text, which is where a label is a label.
Identifiers keep their own names: a test file called
`test_cluster4_index_error.py` and a `TASK_1` constant are code, and a
string that is data (a log message, an API payload, a UI label, a SQL row)
is behaviour, not prose.

Every shape has a positive and a negative case below. When a shape hits
legitimate text (a principle id such as P1, a drawing phase), the shape
narrows; the text stays.
"""
from __future__ import annotations

import io
import re
import tokenize
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src" / "quodeq"
TESTS = REPO / "tests"
SKIP_DIRS = frozenset({"node_modules", "dist", "generated", "__pycache__", "static", "fixtures"})

SHAPES = (
    r"\bTask \d+(?:\.\d+)?\b",                      # Task 4, Task 3.5
    r"\bPlan[ -](?:\d+|[A-Z])\b",                   # Plan B, Plan 1, pre-Plan-A
    r"\b[Cc]luster ?\d+\b",                         # Cluster 12, Cluster36, cluster 25
    r"\bPhase \d+\b(?!:)",                          # Phase 2 (not "Phase 1:" draw steps)
    r"\b[Ww]ave \d+\b",                             # Wave 3
    r"\bWS\d+\b",                                   # WS6
    r"\bP\d+-T\d+\b|(?:^|(?<=//)|(?<=#)|(?<=\())\s*P\d+\b(?=[:\s)])",  # P4-T2, "// P6:", "(P5 ..."
    r"\bB\d+(?:\.\d+)?[a-z]?\b",                    # B4, B5e, B6.2c
    r"\b(?i:audit|review) (?i:findings?) [A-Z]?\d+",  # audit finding C1, Review findings 3
    r"\bAudit [A-Z]\d+\b",                          # Audit A2
    r"\b(?i:finding) \d{3,}\b",                     # finding 5398
    r"\brun [0-9a-f]{8}\b",                         # run 838d807e
    r"\b(?i:fix round)\b",
    r"\b(?i:whole-branch review)\b",
    r"\bCritical \d+\b",                            # Critical 1
    r"\b(?i:cluster|finding|review)s?\W{1,3}M\d+\b",  # review (M8), cluster M3
    r"\bPost-V\d\b",                                # Post-V2
)
LABEL = re.compile("|".join(f"(?:{shape})" for shape in SHAPES), re.MULTILINE)

_STATEMENT_START = (tokenize.INDENT, tokenize.DEDENT, tokenize.NEWLINE, tokenize.NL)


def _iter_sources():
    """Yield src/quodeq .py/.js/.jsx and tests .py files, vendored dirs and this file aside."""
    for root, exts in ((SRC, ("*.py", "*.js", "*.jsx")), (TESTS, ("*.py",))):
        for ext in exts:
            for path in sorted(root.rglob(ext)):
                if SKIP_DIRS.isdisjoint(path.relative_to(root).parts) and path != Path(__file__).resolve():
                    yield path


def python_prose(source: str) -> list[tuple[int, str]]:
    """Return (lineno, text) for every comment and docstring in *source*.

    `tokenize` gives comments directly. A docstring is a STRING token that
    is the whole logical line at bracket depth zero, which is what separates
    it from a string used as a value (including one continuing a call's
    arguments on its own line).
    """
    prose: list[tuple[int, str]] = []
    previous, depth = tokenize.INDENT, 0
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.OP and tok.string in "([{":
            depth += 1
        elif tok.type == tokenize.OP and tok.string in ")]}":
            depth -= 1
        if tok.type == tokenize.COMMENT:
            prose.append((tok.start[0], tok.string))
        elif tok.type == tokenize.STRING and depth == 0 and previous in _STATEMENT_START:
            prose.append((tok.start[0], tok.string))
        if tok.type != tokenize.COMMENT:
            previous = tok.type
    return prose


def js_prose(source: str) -> list[tuple[int, str]]:
    """Return (lineno, text) for every `//` and `/* */` comment in *source*.

    A hand-rolled scanner rather than a regex, so a `//` inside a string or
    a template literal is not read as a comment. Known limitation: a regex
    literal containing `//` or `/*` would be, which no file here has.
    """
    prose: list[tuple[int, str]] = []
    i, line, n = 0, 1, len(source)
    while i < n:
        ch = source[i]
        if ch == "\n":
            line += 1
            i += 1
        elif ch in "'\"`":
            quote, i = ch, i + 1
            while i < n and source[i] != quote:
                if source[i] == "\\":
                    i += 1
                elif source[i] == "\n":
                    line += 1
                i += 1
            i += 1
        elif source.startswith("//", i):
            end = source.find("\n", i)
            end = n if end == -1 else end
            prose.append((line, source[i:end]))
            i = end
        elif source.startswith("/*", i):
            end = source.find("*/", i + 2)
            end = n if end == -1 else end + 2
            body = source[i:end]
            prose.append((line, body))
            line += body.count("\n")
            i = end
        else:
            i += 1
    return prose


def labels_in(text: str) -> list[str]:
    """Every label in one piece of prose, stripped."""
    return [match.group(0).strip() for match in LABEL.finditer(text)]


def collect_labels() -> list[str]:
    """Return `path:line: label -- text` for every label in scoped prose."""
    hits: list[str] = []
    for path in _iter_sources():
        source = path.read_text(encoding="utf-8")
        extract = python_prose if path.suffix == ".py" else js_prose
        for lineno, text in extract(source):
            for match in LABEL.finditer(text):
                # A docstring or block comment is one token spanning many
                # lines; report the line the label is actually on.
                before = text[:match.start()]
                at = lineno + before.count("\n")
                context = " ".join(text.splitlines()[before.count("\n")].split())[:90]
                hits.append(f"{path.relative_to(REPO)}:{at}: {match.group(0).strip()} -- {context}")
    return hits


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
])
def test_label_shape_ignores_legitimate_text(text):
    assert labels_in(text) == []


def test_no_planning_labels_in_prose():
    hits = collect_labels()
    assert hits == [], (
        "Planning or audit labels in comments or docstrings. Say the reason in "
        "prose, or link the repo issue, which still resolves:\n" + "\n".join(hits)
    )
