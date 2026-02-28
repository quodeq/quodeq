# CodeCompass

## Dashboard (Python CLI)

```bash
codecompass dashboard
```

The dashboard command now auto-starts (or reuses) the Python Action API and picks an available port starting at 8001.

### Troubleshooting

- If the browser shows `Cannot GET /` and CSP warnings, the UI server is not serving the built `ui/web/dist` assets. Re-run `codecompass dashboard` without `--no-build`, or ensure `ui/web/dist/index.html` exists. The CSP messages are a symptom of the error page, not the UI itself.

## Action API (manual)

Start the Python Action API:

```bash
uv run python -m codecompass.action_api
```

Then run the UI server with:

```bash
CODECOMPASS_ACTION_API=http://127.0.0.1:8001 uv run codecompass dashboard
```

You can override the Action API host/port for auto-start:

```bash
uv run codecompass dashboard --api-host 127.0.0.1 --api-port 8001
```

## Features
