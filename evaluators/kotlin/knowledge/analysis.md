# Kotlin Codebase Analysis Guidance

## Where to look first

### Security hotspots
- **Hardcoded secrets** — search for `apiKey`, `secret`, `password`, `token` assigned to string literals.
- **SQL injection** — string templates in SQL queries (`"SELECT * FROM users WHERE id = ${id}"`).
- **Insecure deserialization** — Gson/Jackson without type validation.

### Maintainability signals
- **File size** — Kotlin files over 300 LOC suggest SRP violations.
- **God classes** — classes with 10+ public methods or 5+ injected dependencies.
- **Deeply nested when/if** — 3+ levels of nesting reduce readability.

### Reliability signals
- **Empty catch blocks** — swallowed exceptions hide failures.
- **Missing null safety** — `!!` operator overuse bypasses Kotlin's null safety.
- **Unclosed resources** — missing `.use {}` on AutoCloseable instances.

### Performance signals
- **Blocking calls in coroutines** — `Thread.sleep()` or blocking I/O inside `suspend` functions.
- **N+1 queries** — database calls inside loops.
- **Missing lazy initialization** — expensive objects created eagerly when not always needed.
