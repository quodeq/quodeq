# Core Context

This context defines the immutable domain logic, scoring algorithms, and fundamental data models of Quodeq.

## Language

**Evaluator**:
The high-level component that executes a specific **Standard** against a codebase.

**Standard**:
A structured collection of **Principles** (e.g., OWASP ASVS, ISO 25010). It defines the scope, weight, and ruleset of an evaluation.

**Principle**:
A specific rule or practice within a **Standard**. It aggregates multiple **Judgments** to calculate its own compliance metrics and score.

**Requirement / Practice**:
The atomic unit of a **Standard**. It is the specific instruction or rule that the AI is asked to verify.

**Judgment**:
An individual LLM observation. It is the raw "verdict" (`violation`, `compliance`, or `dismissed`) regarding a specific requirement in a piece of code.

**Finding**:
The canonical, structured entity derived from a **Judgment**. It represents a verified violation or compliance event.

**Scoring**:
The multi-level mathematical process of hierarchical aggregation:
1. **Principle Level**: Aggregates **Findings** to compute a principle score.
2. **Standard Level**: Aggregates **Principles** to compute a standard score.
3. **Overall Level**: Aggregates multiple **Standards** to compute the final project score.

**ScoringResult**:
The final, multi-layered output containing the complete hierarchy of scores (Principles, Standards, and Overall).

**Evidence**:
The collection of all data points (judgments, principles, and metrics) required to perform a complete scoring run.

## Relationships

- An **Evaluator** applies a **Standard**.
- A **Standard** is composed of multiple **Principles**.
- Each **Principle** is comprised of several **Requirements**.
- The AI makes **Judgments** against **Requirements**.
- **Judgments** are materialized as **Findings**.
- **Scoring** follows the hierarchical flow: **Findings** $\rightarrow$ **Principles** $\rightarrow$ **Standards** $\rightarrow$ **Overall Score**.
- A **Run** consists of multiple **Standards** (and their constituent **Principles** and **Findings**) across several **Dimensions**.
