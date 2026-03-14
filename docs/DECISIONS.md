## Enhanced Analysis Architecture v4 - 2026-03-11

- Context: Current analysis uses 1 sequential LLM agent per dimension (~10 min, ~50 files, ~24M tokens). Context grows quadratically as conversation history accumulates. Coverage drops to <10% on large repos.
- Options: (A) Keep single agent, increase turns. (B) Parallel subagents with shared JSONL. (C) Static analysis pre-layer + subagents + validation.
- Chosen: Option C — three-tier architecture with SARIF-based static analysis, LLM validation, and focused subagents.
- Rationale: Static analysis covers 100% of files at zero token cost. Subagents eliminate quadratic context growth. LLM focuses only on what requires judgment. Estimated: 3x coverage, 4x fewer tokens, same wall-clock time.
