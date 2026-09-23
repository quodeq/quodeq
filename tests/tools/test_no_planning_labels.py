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

Every shape has a positive and a negative case in test_no_planning_labels_shapes.py.
When a shape hits legitimate text (a principle id such as P1, a drawing
phase), the shape narrows; the text stays.
"""
from __future__ import annotations

import io
import re
import tokenize
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src" / "quodeq"
TESTS = REPO / "tests"
SKIP_DIRS = frozenset({"node_modules", "dist", "generated", "__pycache__", "static", "fixtures"})

SHAPES = (
    r"\b(?i:task) \d+(?:\.\d+)?\b",                 # Task 4, task 3.5 (case-insensitive)
    r"\bPlan[ -](?:\d+|[A-Z])\b",                   # Plan B, Plan 1, pre-Plan-A
    r"\b[Cc]luster ?\d+\b",                         # Cluster 12, Cluster36, cluster 25
    r"\bPhase \d+\b(?!:)",                          # Phase 2 (not "Phase 1:" draw steps)
    r"\b[Ww]ave \d+\b",                             # Wave 3
    r"\bWS\d+\b",                                   # WS6
    r"\bP\d+-T\d+\b|(?:^|(?<=//)|(?<=#)|(?<=\())\s*P\d+\b(?=[:\s)])",  # P4-T2, "// P6:", "(P5 ..."
    r"\bB\d+(?:\.\d+)?[a-z]?\b",                    # B4, B5e, B6.2c
    r"\b(?i:audit|review) (?i:findings?) [A-Za-z]?\d+",  # audit finding C1, review findings d3
    r"\bAudit [A-Z]\d+\b",                          # Audit A2
    r"\b(?i:findings?) \d{3,}\b",                   # finding 5398, findings 5398 (plural-aware)
    r"\b(?i:run) [0-9a-f]{8,}\b",                   # run 838d807e, Run fa56db32e1 (8+ hex)
    r"\b(?i:fix round)\b",
    r"\b(?i:whole-branch review)\b",
    r"\bCritical \d+\b",                            # Critical 1
    r"\b(?i:cluster|finding|review)s?\W{1,3}M\d+\b",  # review (M8), cluster M3
    r"\bPost-V\d\b",                                # Post-V2
    r"\b(?i:(?:fault-tolerance|usability|maintainability|reliability|security"
    r"|performance|flexibility|clean-arch(?:itecture)?|quality) cycle) \d+\b",
    r"\b(?i:review) item [A-Z]\b",                  # review item B (final review item B)
)
LABEL = re.compile("|".join(f"(?:{shape})" for shape in SHAPES), re.MULTILINE)

_STATEMENT_START = (tokenize.INDENT, tokenize.DEDENT, tokenize.NEWLINE, tokenize.NL)


def _iter_sources():
    """Yield src/quodeq .py/.js/.jsx/.mjs and tests .py files, vendored dirs and this file aside."""
    for root, exts in ((SRC, ("*.py", "*.js", "*.jsx", "*.mjs")), (TESTS, ("*.py",))):
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


_REGEX_PRECEDERS = frozenset(
    "return typeof instanceof in of new delete void yield throw case do else await".split()
)


def _regex_starts_here(source: str, i: int) -> bool:
    """Heuristic: does `/` at *i* start a regex literal rather than division?

    True after an operator/opener/newline, or after a keyword that itself
    precedes an expression (``return /x/``); false after a value.
    """
    j = i - 1
    while j >= 0 and source[j] in " \t":
        j -= 1
    if j < 0:
        return True
    c = source[j]
    if c in "([{,;:=&|!?+-*%^~<>\n":
        return True
    if c.isalnum() or c in "_$":
        k = j
        while k >= 0 and (source[k].isalnum() or source[k] in "_$"):
            k -= 1
        return source[k + 1:j + 1] in _REGEX_PRECEDERS
    return False


def _skip_regex(source: str, i: int, n: int):
    """Skip a regex literal opening at *i*; return the index past its
    closing `/` and flags, or None if the line ends first (caller then
    treats `/` as ordinary). A `[...]` class is tracked so a quote or
    backtick inside it (``/[/\\:"<>]/``) never starts a fake string.
    """
    j, in_class = i + 1, False
    while j < n and source[j] != "\n":
        ch = source[j]
        if ch == "\\":
            j += 2
            continue
        if ch == "[":
            in_class = True
        elif ch == "]":
            in_class = False
        elif ch == "/" and not in_class:
            j += 1
            while j < n and source[j].isalpha():
                j += 1
            return j
        j += 1
    return None


def _scan(source: str, i: int, n: int, line: int, prose: list, until):
    """Scan from *i*, appending comments to *prose*. With ``until="}"``
    (a `${...}` substitution) an unmatched `}` ends the scan; a `{` opened
    inside is tracked so it doesn't. Returns (index after, current line).
    """
    depth = 0
    while i < n:
        ch = source[i]
        if ch == "\n":
            line += 1
            i += 1
        elif until == "}" and ch == "{":
            depth += 1
            i += 1
        elif until == "}" and ch == "}":
            if depth == 0:
                return i + 1, line
            depth -= 1
            i += 1
        elif ch in "'\"":
            quote, i = ch, i + 1
            while i < n and source[i] != quote:
                if source[i] == "\\":
                    i += 1
                elif source[i] == "\n":
                    line += 1
                i += 1
            i += 1
        elif ch == "`":
            i, line = _scan_template(source, i + 1, n, line, prose)
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
        elif ch == "/" and _regex_starts_here(source, i):
            skipped = _skip_regex(source, i, n)
            i = skipped if skipped is not None else i + 1
        else:
            i += 1
    return i, line


def _scan_template(source: str, i: int, n: int, line: int, prose: list):
    """Scan a template literal's body (just past its opening backtick) to
    the matching closing one, handling `${...}` substitutions via `_scan`.
    """
    while i < n:
        ch = source[i]
        if ch == "`":
            return i + 1, line
        if ch == "\\":
            i += 2
            continue
        if ch == "\n":
            line += 1
            i += 1
            continue
        if ch == "$" and i + 1 < n and source[i + 1] == "{":
            i, line = _scan(source, i + 2, n, line, prose, until="}")
            continue
        i += 1
    return i, line


def js_prose(source: str) -> list[tuple[int, str]]:
    """Return (lineno, text) for every `//` and `/* */` comment in *source*.

    A hand-rolled scanner, so a `//`/`` ` ``/`/` inside a string, a nested
    `${...}` template substitution or a regex literal's `[...]` class is
    never misread as a comment or a stray string opener.

    Known limitation: `_regex_starts_here` is a heuristic (the character
    before the `/`), so an unusual expression position could misjudge
    regex vs. division; none of the files this gate scans hit that.
    """
    prose: list[tuple[int, str]] = []
    _scan(source, 0, len(source), 1, prose, until=None)
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


def test_no_planning_labels_in_prose():
    hits = collect_labels()
    assert hits == [], (
        "Planning or audit labels in comments or docstrings. Say the reason in "
        "prose, or link the repo issue, which still resolves:\n" + "\n".join(hits)
    )
