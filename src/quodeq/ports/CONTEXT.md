# Ports Context

This context defines the architectural boundaries and communication contracts within Quodeq. It follows the principles of Hexagonal Architecture (Ports and Adapters) to ensure a clear separation between domain logic and infrastructure.

## Language

**Port (Interface)**:
A formal contract (defined via `typing.Protocol` or abstract base classes) that specifies the operations available to a domain layer without revealing the underlying implementation details.

**Adapter (Implementation)**:
The concrete implementation of a Port. For example, a `SQLiteFindingsRepository` is an adapter that implements a `FindingsPort`. Adapters bridge the gap between the application's needs and external technologies.

**Outbound Port (Driving Port)**:
Interfaces used by the domain or application layers to interact with the outside world (e.g., persistence, messaging, external APIs). The domain layer *owns* these ports.

**Inbound Port (Driven Port)**:
Interfaces that allow external actors (like a CLI or a Web API) to interact with the application core.

**Data Port**:
A specialized subset of Outbound Ports dedicated to managing the lifecycle of domain entities (e.g., `Findings`, `Evaluations`, `Dimensions`). They abstract the complexities of the `Event Log` and the `State Store`.

**Repository Pattern**:
The design pattern applied to Data Ports to provide a collection-like interface for accessing domain objects, effectively hiding whether the data resides in a JSONL file, a SQLite database, or a remote service.

## Relationships

- The **Core** and **Services** layers define and use **Ports** to execute business logic.
- **Adapters** implement these **Ports** to connect the application to the filesystem, databases, or cloud providers.
- **Data Ports** serve as the primary interface for the **Engine** and **Services** to interact with the **Event Log** and **State Store**.
- A change in infrastructure (e.g., moving from SQLite to PostgreSQL) should only require a new **Adapter**, leaving the **Ports** and the **Core** untouched.
