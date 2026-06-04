# Data Context

This context defines the terminology used within the persistence and data management layers of Quodeq.

## Language

**Event Log (JSONL)**:
The immutable, append-only record of per-run analysis facts (e.g., judgments). User preferences (dismiss, delete) are out of scope — they are project-level and live outside the Event Log.

**State Store (SQLite)**:
The mutable, consolidated view derived from the Event Log via **Projection**, optimized for UI/API querying.

**Projection**:
The process of deriving the current **State Store** by replaying events from the **Event Log** in order.
_Avoid_: Reconciliation, synchronization.

**Projector**:
The component (`ProjectionEngine`) responsible for executing a **Projection** — either a full rebuild or an incremental update from the last checkpoint.
_Avoid_: Reconciler.

**Repository**:
A data access layer (e.g., `FindingsRepository`) that interacts with the **State Store** to perform CRUD operations.

## Relationships

- The **Projector** reads from the **Event Log** to update the **State Store**.
- The **Repository** provides a structured interface to the **State Store** for the rest of the application.

## Flagged ambiguities

- "Database" was previously used generically — resolved: We distinguish between the **Event Log** (truth) and the **State Store** (view).
