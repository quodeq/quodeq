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

**Project**:
A codebase registered in Quodeq. It owns a collection of **Runs** and persists user preferences (dismissed/deleted findings, standards selection).
_Avoid_: repo, codebase (use Project when referring to the Quodeq entity).

## UI Layer

Screen names in the sidebar map to domain concepts as follows:

**Overview**: the screen showing the aggregated **Findings** of the latest (or selected) **Run** across all **Dimensions**.

**Violations (screen)**: browses **Findings** with `verdict=violation` only. Compliance findings are not shown here — they are visible inside the dimension **Explorer**.

**Evaluate (screen)**: the screen that triggers a new **Run**. "Evaluate" is the action; **Run** is the artifact it produces.

**History**: the screen listing all past **Runs** for a project.
_Avoid_: calling it "runs list" — the canonical UI name is History.

**Map**: a code visualisation of health and violation distribution across the codebase. No backend domain equivalent.

**Projects (screen)**: lists all registered **Projects** with their latest grade and score. Entry point for adding, deleting, or switching projects.

**Standards (screen)**: CRUD interface for **Standards** — create, edit, import, and toggle visibility of evaluation rule sets.

**Explorer**: the per-**Dimension** detail screen. Shows principle breakdown, top offending files, and trend. Called "Explorer" in the UI; route ID is `explorer`.
_Avoid_: calling it "Dimension page" — the canonical UI name is Explorer.

**Principle detail**: drills into a single **Principle** within a Dimension — violations grouped by severity, compliance list, fix-plan side-pane. Route ID: `evalprinciple`.

**File detail**: all **Findings** for a single file across all Dimensions. Route ID: `file`.

**Finding detail**: single **Finding** card with breadcrumb (Overview › Dimension › Principle). Leaf view, no further navigation. Route ID: `finding`.

**Run detail**: single-**Run** snapshot, reuses the Overview screen in run mode. Route ID: `history-run`. Reached from History.

**Settings**: provider configuration (Cloud/CLI/Ollama), appearance, and server info. No domain equivalent.

**Help**: in-app documentation. No domain equivalent.

## Relationships

- An **Analysis** process uses **Core** logic to generate **Findings**.
- A **Run** consists of multiple **Findings** across several **Dimensions**.

## Example dialogue

> **Dev**: "The agent failed to extract the evidence."
> **Domain Expert**: "Is that an issue in the **Analysis** orchestration, or is the **Core** model for evidence too restrictive?"

## Flagged ambiguities

- "Core" was previously used to mean "the most important part of the project" — resolved: **Core** now specifically refers to the domain logic layer.
