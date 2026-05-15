# Services Context

This context defines the application layer of Quodeq. The services layer is responsible for implementing use cases, coordinating domain logic with infrastructure, and preparing data for the user interface.

## Language

**Application Service**:
A high-level component that coordinates business use cases (e.g., "delete a finding", "generate a report"). It orchestrates the interaction between the domain models and the underlying infrastructure.

**Mutation Service**:
Services responsible for processing state changes in the application (e.g., `deleted.py`, `dismissed.py`). In the new architecture, these mutations must be recorded as events in the **Event Log**.

**Indexing Service**:
The logic responsible for maintaining the **State Store** (SQLite) synchronized and updated based on filesystem information and the **Event Log**. It is the bridge that ensures the "audit truth" is reflected in the "query truth".

**Filesystem Provider**:
Services that abstract and manage complex file operations, directories, metadata, and POSIX locks on the disk.

**Dashboard & Analytics Service**:
Services specialized in data aggregation, trend calculation, and cache management to provide an optimized and fast view of the project history to the user interface.

## Relationships

- The **Pipeline Runner** (`engine/`) utilizes **Application Services** to complete an execution run.
- **Mutation Services** write to the **Event Log** and trigger the **Indexing Service**.
- The **Indexing Service** updates the **State Store** (SQLite).
- The **Dashboard Service** queries the **State Store** and the **Filesystem** to build the user interface views.
