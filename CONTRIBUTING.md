# Contributing to Quodeq

Thanks for your interest in contributing. Quodeq is open source and we welcome contributions of all kinds: bug reports, feature requests, documentation improvements, and code.

## Getting Started

```bash
git clone https://github.com/quodeq/quodeq.git && cd quodeq
uv sync
uv run pytest
```

## Building the Web Dashboard

The web dashboard is a Vite + React app at `src/quodeq/ui/`. End users get a pre-built copy inside the wheel and do not need Node.js or npm. Contributors need them in two situations:

1. **Local wheel builds.** `uv build` on its own produces a wheel without the UI. Use `tools/build-dist.sh` instead. It runs `npm ci && npm run build` and then `uv build`, so the wheel ships with `src/quodeq/static/` populated.
2. **Iterating on the UI source.** `quodeq dashboard --dev` rebuilds the UI from `src/quodeq/ui/` on the fly. This is the only runtime codepath that still invokes npm.

Minimum dev versions: Python 3.12+, Node.js 20+, npm 10+.

## How to Contribute

### Reporting Bugs

Open an issue using the **Bug Report** template. Include:

- What you expected to happen
- What actually happened
- Steps to reproduce
- Your OS, Python version, and Quodeq version (`quodeq --version`)

### Suggesting Features

Open an issue using the **Feature Request** template. Describe the problem you are trying to solve, not just the solution you have in mind.

### Submitting Code

1. Fork the repo and create a branch from `develop`
2. Make your changes
3. Run the tests: `uv run pytest`
4. Open a pull request targeting `develop`

Keep pull requests focused on a single change. If you are fixing a bug and also want to refactor something, open two PRs.

### Code Style

- Follow the existing patterns in the codebase
- No need to add docstrings or type annotations to code you did not change
- Tests go in `tests/` mirroring the `src/` structure

## Branch Model

- `main` is for releases only
- `develop` is the active development branch
- Feature branches go `feature/your-branch` -> `develop` via PR

## Security

If you find a security vulnerability, do not open a public issue. Email quodeq.ai@gmail.com instead. See [SECURITY.md](SECURITY.md) for details.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
