# Python Codebase Analysis Guidance

## Where to look first

### Security hotspots
- **eval()/exec()** — any occurrence in non-test code is a finding.
- **Hardcoded secrets** — `api_key`, `secret`, `password`, `token` assigned to string literals.
- **Command injection** — `os.system()`, `subprocess` with `shell=True`.
- **SQL injection** — f-strings or string formatting in SQL queries.

### Maintainability signals
- **File size** — Python files over 300 LOC suggest SRP violations.
- **Cyclomatic complexity** — deeply nested if/for/try blocks.
- **Missing type hints** — function signatures without type annotations.

### Reliability signals
- **Bare except clauses** — `except:` or `except Exception:` without specific handling.
- **Missing context managers** — file handles without `with` statement.
- **Unchecked return values** — ignoring return values from functions that can fail.

### Performance signals
- **N+1 queries** — database calls inside loops.
- **Missing generators** — loading entire datasets into memory when streaming would work.
- **Synchronous I/O in async code** — blocking calls in async functions.
