# Data Context

This context defines the terminology used within the persistence and data management layers of Quodeq.

## Language

**Event Log (JSONL)**:
The immutable, append-only record of all facts and actions occurring during an evaluation.

**State Store (SQLite)**:
The mutable, consolidated projection of the Event Log, optimized for UI/API querying.

**Reconciliation**:
The process of synchronizing the **State Store** with the **Event Log** to ensure consistency.

**Reconciler**:
The component (e.g., `RunIndexReconciler`) responsible for executing the reconciliation process.

**Repository**:
A data access layer (e.g., `FindingsRepository`) that interacts with the **State Store** to perform CRUD operations.

**Projection**:
The resulting view or data set created by the reconciliation process.

## Relationships

- The **Reconciler** reads from the **Event Log** to update the **State Store**.
- The **Repository** provides a structured interface to the **State Store** for the rest of the application.

## Flagged ambiguities

- "Database" was previously used generically — resolved: We distinguish between the **Event Log** (truth) and the **State Store** (view).
