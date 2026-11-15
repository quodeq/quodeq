## Why quodeq

quodeq reads your code the way a reviewer would and reports both what is wrong and what is right. It is not a linter: it evaluates meaning, not syntax.

### Why it exists

Traditional code-quality tools count syntax violations. They flag a long function or a missing null check, but they cannot tell you that your architecture leaks dependencies or that your domain model has eroded.

quodeq gives an AI model you choose read-only access to your repository. The model follows imports, understands patterns, and evaluates the code against structured standards. It never changes a file. Every finding cites a file, a line, a code snippet, and the principle it concerns.

### How an evaluation runs

1. **Detect** identifies languages, frameworks, and structure.
2. **Analyze** runs parallel sub-agents that read files with read-only tools.
3. **Collect** streams findings live as the agents work.
4. **Score** maps findings to principles and computes a score per principle and per dimension.
5. **Report** produces grades, trend deltas, and a fix plan per dimension.

### Both sides of the story

quodeq reports **violations and compliance**. Compliance is counted in the same unit as violations and lifts the score, so a project with many violations but strong compliance patterns scores more fairly than one with the same violations and no evidence of good practice. The agents look for files that follow standards correctly, not just files that break them.

### How the grade is computed

Each principle is scored 0 to 10 in four stages: the broken rules, weighted by how widely each is broken; a base score; a lift from compliance; and a ceiling and a floor. *Why This Grade* explains the stages in words, and *Grade Formula* shows every parameter on your own run and lets you tune it.

### What it evaluates

quodeq ships with six dimensions from ISO 25010, plus Clean Architecture, DDD, WCAG 2.2 Accessibility and AI Integration Security as opt-in standards (*Quality Dimensions*). It works in any language, and you can write your own standards for whatever quality means in your project (*Custom Standards*).
