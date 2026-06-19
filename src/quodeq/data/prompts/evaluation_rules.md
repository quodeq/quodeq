## Look for

Bad patterns, vulnerabilities, anti-patterns. Missing error handling, validation, logging, retries, abstractions.

Report BOTH violations AND compliance. Scoring is a ratio. For every principle with violations, also look for compliant files.

Report each occurrence separately. 5 misplaced methods = 5 findings.

NOT a violation: literal inside a constant/enum definition; long function that only registers routes; duplicated test setup; code that IS the remediation for the issue; the flagged line or its neighbour already contains the guard (`escapeHtml`, `length` check, null guard, `try`/`catch`); algorithm-intrinsic complexity (force-directed layout, MST, per-frame trig); count equals limit (`max 5` is `> 5`, not `>= 5`).

## Evidence

Code must be visible in source.

DROP if you can only point to absence, imports, paths, or module layout (unless the requirement explicitly demands the missing code be present in this file).

DROP speculative concerns: "could", "might", "should consider".

## Severity

- **critical** — Exploitable vulnerability or production-breaking bug, demonstrable from code as-is. SQL injection with user input reaching raw query; hardcoded secret; auth bypass; data loss on a real path. Hardening gaps, defense-in-depth, hypotheticals → NOT critical.
- **major** — Real quality or security issue. Should be fixed. Not directly exploitable.
- **minor** — Real defect in the quoted code: style violation, measurable inefficiency, concrete improvement. NOT a fallback for findings that fail the higher bar.

Compliance uses the same scale to mark importance of what's done right.

## Reachable input (provenance)

A missing null/guard check (R-FT-2) or a path/key built from a value (S-AUT-3) is `critical` only when a bad value can reach the flagged line. Name the caller or source that delivers it.

Internal input is NOT `critical`. The value is internal when it is a content hash or digest, a module-level constant or enum, a parameter with a default, or a value every visible call site passes valid (a React prop from a hook/default, an argument always given a literal). A missing guard on internal input is a hardening gap → `major` if 1–4 hold and the guard is genuinely worth adding, else drop.

External input stays `critical`. The value reaches the line from an HTTP request, query string, request body, CLI argument, environment variable, file contents, or any caller across a trust boundary.

Not `critical`:
- `stack.forEach(...)` on a prop with no null guard, where the prop is supplied by a hook or a default at every call site.
- `[...thresholds]` or destructuring a hook argument whose value is backfilled from defaults.
- a cache path `root / key[:2] / key[2:]` where `key` is a SHA-256 hex digest (or validated against a safe charset); the digest is not attacker-controlled.

Genuinely `critical`:
- a path built from `request.args["file"]`, or a dereference of a value parsed from an HTTP request body; provenance is external.

## Test files

Test file → max severity `minor`. Never `critical`/`major` on tests, fixtures, mocks, or specs.

Test files contain `eval(x)`, secrets, path-traversal payloads on purpose. A real issue surfaces as `minor`; that's enough.

## Self-check (every finding, including minor)

1. **Evidence** — Quote the problem line. Only "missing"/"absent" → drop.
2. **Concrete** — State the problem about the quoted code and name the concrete impact (what breaks, who is affected, or what attack/failure it enables).
3. **No hedging** — No "could", "might", "may", "should consider", "if X were larger", "if async", "in a hot path". Describe what the line does wrong AS WRITTEN.
4. **Impact** — Name the observable consequence. "Could be slow under load" without a profile is speculation.

For `critical`/`major` also:

5. **Attack/failure** — Describe specific attack or failure this code enables as written. Hedge words → `minor` only if 1–4 hold; else drop.
6. **Reachable** — Production code path. Tests, examples, dev scaffolding are not `critical`.
7. **Provenance** (unguarded access & path-from-string only) — Name the caller or external source that delivers a bad or attacker-controlled value to this line. Can't, because the value is a content hash, a constant, a defaulted parameter, or always a literal at the call sites you see? Not `critical` → `major` if 1–4 hold, else drop.

**Decision**: 1–4 fail → DROP entirely. 5–6 fail → `minor` only if 1–4 hold, else drop. 7 fail → `major` (or drop) per the item. `minor` is not a fallback bucket.

Fewer sharper findings beats long reports padded with speculation.
