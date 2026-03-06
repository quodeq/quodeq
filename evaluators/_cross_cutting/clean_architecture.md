# Clean Architecture — Cross-Cutting Knowledge

Applies to all runtimes. Use these as the lens when assessing structural and maintainability findings.

## The Dependency Rule
Source code dependencies must point inward. Inner layers know nothing about outer layers.

```
[Frameworks & Drivers] → [Interface Adapters] → [Use Cases] → [Entities]
```

**Violation signals:**
- Domain models importing from HTTP controllers or database adapters
- Use cases importing Express/Fastify types directly
- Business rules depending on a specific ORM

## Layer definitions

### Entities (innermost)
Pure business objects and rules. No I/O, no framework dependencies.

```typescript
// Good — entity has no dependencies
class Order {
  constructor(readonly id: string, readonly items: OrderItem[]) {}
  get total(): number { return this.items.reduce((sum, i) => sum + i.price, 0); }
}
```

### Use Cases
Application-specific business rules. Depends on entities + repository interfaces (not implementations).

```typescript
// Good — use case depends on interface, not concrete DB
interface OrderRepository { findById(id: string): Promise<Order | null>; }

class ProcessOrderUseCase {
  constructor(private repo: OrderRepository) {}
  async execute(orderId: string): Promise<void> { ... }
}
```

### Interface Adapters
Converts data between use cases and the outside world (controllers, presenters, gateways).

### Frameworks & Drivers (outermost)
Express, database drivers, external APIs. Should be swappable without touching inner layers.

## Common architectural smells

| Smell | Description | Finding type |
|---|---|---|
| Fat controllers | Business logic in HTTP handlers | SRP violation |
| God services | One service class orchestrating everything | SRP + DIP violation |
| Import leakage | Domain importing framework types | DIP violation |
| Anemic domain | Entities with no behavior, all logic in services | SRP violation |
| Missing anti-corruption layer | Direct use of third-party models in domain | OCP violation |
