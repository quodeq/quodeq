"""Gate: no planning labels in the prose of src/quodeq.

`Task 4`, `Plan B` and `Cluster 12` are coordinates in a plan that was
closed months ago. To the next reader they name nothing: there is no
artifact to look up, so the sentence they appear in loses whatever reason
it was meant to carry. The fix is never to delete the sentence, it is to
say the reason in prose (or link the repo issue, which still resolves).

Scoped to comment and docstring text, which is where a label is a label.
Identifiers keep their own names: a test file called
`test_cluster4_index_error.py` and a `TASK_1` constant are code, renamed
(if at all) by whoever owns them, and a string that is data (a log
message, an API payload, a UI label) is behaviour, not prose.

Landed red at 95 hits and cleared in the same PR, the same way the
private-import gate did. The tree is at zero now, so a new label fails
here rather than being grandfathered.
"""
from __future__ import annotations

import io
import re
import tokenize
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "quodeq"
SKIP_DIRS = frozenset({"node_modules", "dist", "generated", "__pycache__", "static"})

LABEL = re.compile(r"\bTask \d+\b|\bPlan [A-Z]\b|\bCluster ?\d+\b")


def _iter_sources():
    """Yield every .py/.js/.jsx file under src/quodeq, vendored dirs aside."""
    for ext in ("*.py", "*.js", "*.jsx"):
        for path in sorted(SRC.rglob(ext)):
            if SKIP_DIRS.isdisjoint(path.relative_to(SRC).parts):
                yield path


def python_prose(source: str) -> list[tuple[int, str]]:
    """Return (lineno, text) for every comment and docstring in *source*.

    `tokenize` gives comments directly. A docstring is a STRING token that
    is the whole logical line, which is what separates it from a string
    used as a value.
    """
    prose: list[tuple[int, str]] = []
    previous = tokenize.INDENT
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.COMMENT:
            prose.append((tok.start[0], tok.string))
        elif tok.type == tokenize.STRING and previous in (
            tokenize.INDENT, tokenize.DEDENT, tokenize.NEWLINE, tokenize.NL,
        ):
            prose.append((tok.start[0], tok.string))
        if tok.type not in (tokenize.COMMENT,):
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


def collect_labels() -> list[str]:
    """Return `path:line: text` for every planning label in src/quodeq prose."""
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
                hits.append(f"{path.relative_to(SRC.parents[1])}:{at}: "
                            f"{match.group(0)} -- {context}")
    return hits


def test_python_prose_reads_comments_and_docstrings_only():
    prose = python_prose(
        '"""Module doc."""\n'
        "# a comment\n"
        "X = 'a value'\n"
        "def f():\n"
        "    '''Function doc.'''\n"
        "    return 'another value'\n"
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


def test_label_pattern_matches_the_three_shapes():
    assert LABEL.findall("Task 4, Plan B, Cluster 12, Cluster36") == [
        "Task 4", "Plan B", "Cluster 12", "Cluster36",
    ]
    assert LABEL.findall("tasks 4, planning, clustered") == []


def test_no_planning_labels_in_src_prose():
    hits = collect_labels()
    assert hits == [], (
        "Planning labels in comments or docstrings. Say the reason in prose, "
        "or link the repo issue, which still resolves:\n" + "\n".join(hits)
    )
