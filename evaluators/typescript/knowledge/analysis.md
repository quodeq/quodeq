# TypeScript Codebase Analysis Guidance

## Where to look first

### Security hotspots
- **eval() and new Function()** — search `eval(`, `new Function(`. Any occurrence in non-test code is a finding.
- **Hardcoded secrets** — search for `apiKey`, `secret`, `password`, `token` assigned to string literals ≥8 chars. Flag anything not reading from `process.env`.
- **SQL/command injection** — template literals passed to database query methods (`db.query(\`SELECT ${input}\``)) or `child_process.exec`.

### Maintainability signals
- **File size** — TypeScript files over 300 LOC are a smell. Over 500 LOC is a strong signal of violated SRP.
- **Cyclomatic complexity** — functions with deeply nested if/switch/try blocks (3+ levels) are hard to test.
- **Cross-feature imports** — `import { X } from '../../other-feature/...'` indicates feature coupling. Should go through a shared module or be co-located.
- **Barrel export sprawl** — `index.ts` files with 10+ `export *` re-exports hide what the public API actually is.

### Reliability signals
- **Unhandled Promises** — `.then()` without `.catch()`, or async functions called without `await` and no error handler.
- **Missing null checks** — non-null assertions (`!`) on values that could genuinely be null/undefined.
- **Files without tests** — a `.ts` source file with no matching `.test.ts` or `.spec.ts` is untested by convention.

### Performance signals
- **Sequential awaits** — two or more `await` calls in sequence on independent operations. Should be `Promise.all`.
- **Missing timeouts** — `fetch()` or HTTP client calls without an `AbortController` timeout.
- **N+1 patterns** — a database call inside a loop (look for `await` inside `for`, `forEach`, `map`).

## What to ask the LLM

When presenting findings to the LLM judge, ask it to:
1. Confirm whether each grep hit is a genuine issue or a false positive (test code, commented code, demo)
2. Assess severity in context — a hardcoded secret in a test fixture is different from one in production config
3. Identify compound patterns — e.g. both large files AND no tests in the same module suggests a systemic maintainability problem
4. Map each confirmed finding to the most specific ISO 25010 sub-characteristic and ASVS ID

## Common false positives
- `eval` inside `*.test.ts` or `*.spec.ts` — testing dynamic behavior
- `password` in `createPasswordHash()` function name — not a credential
- Cross-module imports in `__tests__/` — test setup legitimately crosses boundaries
- Large files that are auto-generated (`.d.ts`, `*.generated.ts`)
