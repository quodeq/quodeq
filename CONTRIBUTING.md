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
   CI enforces a coverage floor (80%, see `fail_under` in `pyproject.toml`); reproduce locally with
   `uv run pytest tests/ -q -m "not integration" --cov=quodeq`.
4. Open a pull request targeting `develop`

Keep pull requests focused on a single change. If you are fixing a bug and also want to refactor something, open two PRs.

### Code Style

- Follow the existing patterns in the codebase
- Lint with ruff before pushing. The rule set lives in `pyproject.toml` and the test suite fails on any finding:

      uv run ruff check src/quodeq tests tools
      uv run ruff check --fix src/quodeq tests tools   # autofix the safe ones
- No need to add docstrings or type annotations to code you did not change
- Tests go in `tests/` mirroring the `src/` structure
- Constants: a literal with meaning gets a name where it is used, with a one-line comment saying why it has that value.
  - Python: module-level `_UPPER_SNAKE = value  # reason`. Shared inside a package: that package's `_constants.py`. Shared across packages: `quodeq/shared/constants.py` (`core` may not import `shared`, so anything `core` needs lives under `core/`). HTTP statuses use `http.HTTPStatus`. Ruff `PLR2004` fails the build on a bare number in a comparison; a `len(x) == N` check before an unpack is not a constant, unpack instead or `# noqa: PLR2004  # reason`. `tools/check_magic_numbers.py` fails the build on a bare number used as a call argument, keyword value, parameter default, return value or comparison operand (0, 1, -1, 2, arithmetic, indices, `range`/`round`/`min`/`max` arguments and constant definitions excepted); its baseline is empty. `tools/check_magic_strings.py` fails the build on a bare string the code compares against or repeats 3+ times in a module (dict keys, keyword values, messages and docstrings excepted).
  - UI: module-level `const UPPER_SNAKE = value; // reason`. Shared inside a feature: that feature's constants module. App-wide storage keys, event names, DOM attributes, media queries and breakpoints: `src/constants.js`; unit conversions: `src/utils/time.js`. `npm run lint:magic` fails the build on a bare number other than -1, 0, 1 and 2 outside object literals, array indices and defaults; its baseline is empty. `npm run lint:magic-strings` is the same gate for the UI (object keys and values, JSX attributes and `t()` keys excepted); both baselines are empty.
  - Tests keep asserting the literal value: the literal is the contract, the constant is the implementation.
- Accessibility: interactive elements are real buttons, or carry `role`, `tabIndex` and `activateOnKey` (`src/utils/a11y.js`); names go through `t()`. `npm run lint:a11y` ratchets jsx-a11y violations per file (`tools/a11y_baseline.json` may only shrink).

#### API error responses

Every error response from `src/quodeq/api` carries a machine-readable `code`: build it with `error_response(message, status, code)` from `quodeq.api.helpers`, not a bare `jsonify({"error": ...})`. `code` is an UPPER_SNAKE literal; reuse an existing spelling for the same condition (grep `src/quodeq/api` first) rather than inventing a new one. Route modules do not call `abort()`. Raise a small exception and handle it with `@app.errorhandler`, or return `error_response(...)` directly, so the body keeps the `{"error", "code"}` shape instead of Flask's default error page. `tools/check_error_codes.py` enforces this with a zero-tolerance gate: under `src/quodeq/api`, a `jsonify({"error": ...})` or a `return {"error": ...}, <400+>` without a `"code"` key, or an `abort(400+)`, fails the build. A dict literal whose `"error"` value is `None` is exempt: that is a reserved slot in a success payload, not an error response.

## Branch Model

- `main` is for releases only
- `develop` is the active development branch
- Feature branches go `feature/your-branch` -> `develop` via PR

## Security

If you find a security vulnerability, do not open a public issue. Email quodeq.ai@gmail.com instead. See [SECURITY.md](SECURITY.md) for details.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
