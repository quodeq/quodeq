# SOLID Principles — Cross-Cutting Knowledge

Applies to all runtimes. Use these as the lens when assessing maintainability findings.

## Single Responsibility Principle (SRP)
A class or module should have one reason to change.

**Violation signals:**
- A service class that handles HTTP parsing, business logic, and database writes
- A file named `utils.ts` with unrelated helper functions
- Functions over 50 lines mixing validation, transformation, and I/O

**TypeScript example:**
```typescript
// Bad — UserService doing too much
class UserService {
  parseRequest(req: Request): UserInput { ... }
  validate(input: UserInput): boolean { ... }
  hashPassword(password: string): string { ... }
  save(user: User): Promise<void> { ... }
  sendWelcomeEmail(email: string): Promise<void> { ... }
}

// Good — separated concerns
class UserParser { parseRequest(req: Request): UserInput { ... } }
class UserValidator { validate(input: UserInput): boolean { ... } }
class PasswordService { hash(password: string): string { ... } }
class UserRepository { save(user: User): Promise<void> { ... } }
class EmailService { sendWelcome(email: string): Promise<void> { ... } }
```

## Open/Closed Principle (OCP)
Open for extension, closed for modification. Add behavior by adding code, not changing existing code.

**Violation signals:** `switch` or `if/else if` chains that must grow every time a new type is added.

## Liskov Substitution Principle (LSP)
Subclasses must be usable wherever the base class is expected.

**Violation signals:** Overriding a method to throw `NotImplementedError`, narrowing parameter types in subclasses.

## Interface Segregation Principle (ISP)
Clients should not depend on methods they don't use.

**Violation signals:** Interfaces with 10+ methods where each implementation only uses 3-4.

## Dependency Inversion Principle (DIP)
Depend on abstractions, not concretions. High-level modules should not import low-level modules directly.

**Violation signals:** Business logic importing specific database drivers or HTTP clients directly; no injection mechanism.
