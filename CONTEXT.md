# Quodeq Context

Quodeq is an AI-powered code quality and security scanner that evaluates codebases against ISO 25010 dimensions.

## Language

**Core**:
The immutable domain logic, scoring algorithms, and data models (e.g., evidence models, scoring formulas).
_Avoid_: The entire project, the main engine.

**Event Log (JSONL)**:
The immutable, append-only record of all facts and actions occurring during an evaluation (e.g., `finding_detected`, `finding_deleted`). It is the ultimate source of audit truth.

**State Store (SQLite)**:
The mutable, consolidated projection of the Event Log. It represents the "current reality" (e.g., active findings, current scores) and is optimized for high-speed querying by the UI.

**Dimension**:
A specific axis of evaluation (e.g., Security, Reliability, Maintainability) based on ISO 25010.
_Avoid_: Error, bug.

**Finding/Violation**:
An instance where the code fails to meet a requirement of a dimension, mapped to a CWE.
_Avoid_: Error, bug.

**Run**:
A single execution of the evaluation pipeline on a specific codebase.

## Relationships

- An **Analysis** process uses **Core** logic to generate **Findings**.
- A **Run** consists of multiple **Findings** across several **Dimensions**.

## Example dialogue

> **Dev**: "The agent failed to extract the evidence."
> **Domain Expert**: "Is that an issue in the **Analysis** orchestration, or is the **Core** model for evidence too restrictive?"

## Flagged ambiguities

- "Core" was previously used to mean "the most important part of the project" — resolved: **Core** now specifically refers to the domain logic layer.
