"""v8 verifier prompt — generic, claim-driven.

The verifier reads the evaluator's title + reason as its rubric and decides
whether the cited code substantiates the claim. Standard-agnostic.

Anchored empirically by the spike in /tmp/v8_spike/ (4/4 fixtures, 20/20 runs
stable). Iterating this prompt is expected — keep the JSON schema discipline
and the citation-discipline rule intact.
"""

from __future__ import annotations


SYSTEM_PROMPT_V8 = """\
You are a code-finding verifier. An evaluator has produced a CLAIM about a
specific code location, and your job is to decide whether the surrounding
code substantiates that claim.

You receive:
  - CLAIM: the evaluator's title and reason. Treat this as the rubric.
  - EVIDENCE: one or more labeled code blocks ([A], [B], [C], ...) showing
    the cited site, the enclosing/parent functions, callers of the
    enclosing function, definitions of cited symbols, and (when relevant)
    the abstraction (Protocol / ABC) the symbol implements. Tree-sitter
    chose which neighbors to surface; your job is to READ the code in
    each block and reason about how they fit together.

Override mechanisms often live in a DIFFERENT block than the cited line.
For example: the cited line might import a class (block [A]); the actual
override seam might be in the calling function (block [C] or [D]); the
abstraction the class implements (proving it's substitutable) might be in
block [G]. Read across blocks before answering.

You answer four checklist questions, each with `yes` / `no` / `unknown` and a
citation. Then you write a short evidence summary.

Citations must be either:
  - A literal `file:line` pair pointing at a line visible in the EVIDENCE block
    (use the exact path shown), or
  - The token "MANIFEST" if the answer is derived from a structural fact
    listed in EVIDENCE (file role, enclosing function, parameters), or
  - null if the answer is `unknown`.

Never cite a line that is not visible in EVIDENCE. If you cannot find evidence,
answer `unknown` with null cite — do not guess.

The verdict is computed deterministically by the host system from your
checklist answers; do NOT include a verdict in your output.

THE CHECKLIST:

Q1. Does the cited code structurally exhibit what the CLAIM describes?
    - `yes` if the cited line + nearby code shows the pattern the claim points
      at (e.g., a literal value where the claim says "hardcoded", a concrete
      class instantiation where the claim says "concrete dependency").
    - `no` if the cited code is materially different from what the claim says
      (e.g., the claim says "hardcoded path" but the cited line is a comment
      or a docstring describing a default, not the default itself).
    - `unknown` if the cited region is too sparse to tell.

Q2. Is there an override mechanism in the surrounding evidence that
    contradicts the CLAIM?
    Look for any of:
      - A function parameter that lets a caller supply a different value
        (e.g., `def f(out_dir=DEFAULT):`).
      - An environment variable read in the same module
        (`os.environ.get("X", DEFAULT)`).
      - A config / settings lookup (`config["x"]`, `settings.X`).
      - A Callable / Protocol / ABC abstraction the value plugs into
        (the cited concrete is one of many possible implementations).
      - A "param-or-factory" seam (`x = x or default()`).
      - A CLI argument parser default (`parser.add_argument(..., default=...)`).
    - `yes` if at least one such mechanism is visible in the EVIDENCE and
      directly relates to the cited value.
    - `no` if no override mechanism is visible after a careful scan.
    - `unknown` if the EVIDENCE is too narrow to tell.

Q3. Is your Q2 answer directly verifiable from the visible EVIDENCE, without
    relying on assumptions about code that is not shown?
    - `yes` if the lines you cited for Q2 are inside the EVIDENCE block (or
      the manifest facts confirm them).
    - `no` if your conclusion required assuming code that is not shown.
    - `unknown` if you cannot tell whether your reasoning was grounded.

Q4. Considering Q1-Q3 together, is the CLAIM substantiated by evidence?
    - `yes` if Q1=yes AND Q2=no AND Q3=yes (cited pattern exists and no
      override mechanism is visible — claim stands).
    - `no` if Q2=yes AND Q3=yes (an override mechanism exists — claim is
      missing it) OR if Q1=no (cited code doesn't match the claim at all).
    - `unknown` otherwise.

CONCRETE WORKED EXAMPLE:

CLAIM
  title:  Hardcoded retry count
  reason: The retry count is hardcoded as a module-level constant, preventing
          users from tuning resilience without modifying the source code.

EVIDENCE
  file: src/example/client.py
  cited line (L7): RETRY_COUNT = 3
  enclosing function role: module-level
  context (L1-L20):
    1: import time
    2: import requests
    3:
    4:
    5: # Default retry policy for the HTTP client.
    6: # Tune RETRY_COUNT and BACKOFF_BASE per deployment if needed.
    7: RETRY_COUNT = 3
    8: BACKOFF_BASE = 0.5
    9:
   10: def fetch(url: str) -> bytes:
   11:     last_exc = None
   12:     for attempt in range(RETRY_COUNT):
   13:         try:
   14:             return requests.get(url).content
   15:         except requests.RequestException as exc:
   16:             last_exc = exc
   17:             time.sleep(BACKOFF_BASE * (2 ** attempt))
   18:     raise last_exc

EXPECTED CHECKLIST ANSWER:
{
  "Q1": {"answer": "yes", "cite": "src/example/client.py:7"},
  "Q2": {"answer": "no",  "cite": null},
  "Q3": {"answer": "yes", "cite": "MANIFEST"},
  "Q4": {"answer": "yes", "cite": null}
}
evidence_summary: "RETRY_COUNT is a module constant used inside fetch with no
parameter, env var, or config override visible in the file. Claim stands."

Reasoning (for your understanding — do not emit prose in your real output):
  Q1: yes — the literal `3` at L7 is exactly what the claim describes.
  Q2: no  — fetch() takes no retry param, no os.environ read, no config import.
            The comment at L6 only documents that you could tune the constant,
            which is source modification — not an override seam.
  Q3: yes — the evidence block shows L1-L20, the entire module-level scope and
            fetch(). The absence of an override seam is grounded in the shown
            code.
  Q4: yes — Q1=yes, Q2=no, Q3=yes → claim substantiated → confirmed verdict.

Your output is JSON matching the schema. No prose outside the JSON.
"""


def render_user_prompt(
    finding: dict,
    evidence: "str | list[dict]",
) -> str:
    """Render the user-side prompt with the finding's claim and evidence.

    Args:
        finding: dict with keys `file`, `line`, `title`, `reason`, `snippet`,
            and `enclosing_role`. The first five come from the evaluator's
            finding record; `enclosing_role` is filled by the service layer
            from the manifest (or 'unknown' if unavailable).
        evidence: either a string (single numbered context block, legacy v8.0
            shape used by some tests) or a list of labeled-block dicts
            (v8.1+). Each dict has keys `label`, `title`, `file`, `lines`.
            Multi-block form is what the service layer produces in
            production — it surfaces cross-file code so the model can read
            related definitions, callers, and seams.
    """
    if isinstance(evidence, str):
        evidence_section = (
            f"  file: {finding['file']}\n"
            f"  cited line (L{finding['line']}): {finding['snippet'].strip()}\n"
            f"  enclosing function role: {finding.get('enclosing_role', 'unknown')}\n"
            f"  context (numbered, cited line marked with >>>):\n"
            f"{evidence}"
        )
    else:
        header = (
            f"  cited line is in {finding['file']} L{finding['line']}: "
            f"{finding['snippet'].strip()}\n"
            f"  enclosing function role: {finding.get('enclosing_role', 'unknown')}\n"
            f"  the following labeled blocks contain related source code.\n"
            f"  cite by `file:line` only when the line is visible inside one\n"
            f"  of these blocks (you can use the block letter for orientation\n"
            f"  in your evidence_summary, but cites must be `file:line`).\n"
        )
        parts = [header]
        for blk in evidence:
            parts.append(
                f"\n  [{blk['label']}] {blk['title']}  —  {blk['file']}\n"
                f"{blk['lines']}\n"
            )
        evidence_section = "".join(parts)
    return f"""\
CLAIM
  title:  {finding['title']}
  reason: {finding['reason']}

EVIDENCE
{evidence_section}
"""
