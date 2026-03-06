# iOS / Swift Codebase Analysis Guidance

## Where to look first

### Security hotspots
- **Hardcoded secrets** — API keys, tokens, or passwords in Swift string literals.
- **UserDefaults for secrets** — tokens or passwords stored unencrypted.
- **Insecure network** — HTTP instead of HTTPS, disabled ATS.

### Maintainability signals
- **Massive view controllers** — files over 300 LOC, especially UIViewControllers.
- **Missing MVVM/Coordinator** — business logic mixed into view layer.
- **Storyboard sprawl** — single storyboard with 10+ scenes.

### Reliability signals
- **Force unwrap (!)** — crashes on nil values at runtime.
- **Missing error handling** — `try!` or unhandled throws.
- **Retain cycles** — missing `[weak self]` in closures.

### Performance signals
- **Main thread blocking** — network calls or heavy computation on main queue.
- **Missing image caching** — reloading images without cache.
- **Large view hierarchies** — deeply nested views without lazy loading.
