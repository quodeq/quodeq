# Java Codebase Analysis Guidance

## Where to look first

### Security hotspots
- **Hardcoded secrets** — string literals assigned to `apiKey`, `secret`, `password` fields.
- **SQL injection** — string concatenation in SQL queries instead of PreparedStatement.
- **Insecure deserialization** — ObjectInputStream without type validation.

### Maintainability signals
- **File size** — Java files over 300 LOC are a code smell.
- **God classes** — classes with 10+ public methods or excessive constructor parameters.
- **Deep inheritance** — more than 3 levels of class hierarchy.

### Reliability signals
- **Catch generic Exception** — swallowing all exceptions hides bugs.
- **Missing resource cleanup** — streams/connections without try-with-resources.
- **Unchecked null returns** — methods returning null without @Nullable annotation.

### Performance signals
- **String concatenation in loops** — `+=` with String instead of StringBuilder.
- **Synchronous blocking** — Thread.sleep() or blocking I/O on event loop threads.
- **N+1 queries** — JPA lazy loading triggering queries inside loops.
