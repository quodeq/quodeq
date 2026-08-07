## The Quodeq Philosophy

Quodeq reads your code the way a reviewer would and reports both what is wrong and what is right. It is not a linter: it evaluates meaning, not syntax.

### Why Quodeq exists

Traditional code-quality tools count syntax violations. They flag a long function or a missing null check, but they cannot tell you that your architecture leaks dependencies or that your domain model has eroded.

Quodeq sends AI agents into your codebase with read-only tools to explore, follow imports, understand patterns, and evaluate quality against structured standards. Every finding cites a file, a line, a code snippet, and a principle.

### How an evaluation runs

1. **Detect** identifies languages, frameworks, and structure.
2. **Analyze** spawns parallel sub-agents with read-only tools (Bash, Grep, Read, Glob).
3. **Collect** streams structured findings (JSONL) live as the agents work.
4. **Score** maps findings to principles and computes per-dimension scores.
5. **Report** produces grades, trend deltas, and per-finding fix plans.

### Both sides of the story

Quodeq reports **violations and compliance**. Scoring uses the ratio between them, so a project with many violations but strong compliance patterns scores more fairly than one with the same violations and no evidence of good practice. Agents actively look for files that follow standards correctly, not just files that break them.

### The Q² scoring formula

Each principle is scored 0 to 10 under four constraints.

- A hyperbolic **violation base** means the first violations hurt most. Fifty minor issues will not tank a score the way five critical ones do.
- A **compliance lift** fills the gap between the base and 10 with evidence of good practice, so compliance always helps and never hurts.
- A log-based **violation ceiling** stops compliance from masking real problems. You cannot reach *Exemplary* with critical issues in play.
- A **severity grade floor** keeps the label honest. Only an actual critical violation can produce a *Critical* grade.

Quodeq ships with ISO 25010 dimensions plus Clean Architecture and DDD. It works in any language, and you can write your own standards for whatever quality means in your project.
