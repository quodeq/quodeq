# Quodeq UI Dashboard

Local dashboard for analyzed projects under `reports/`.

## Structure

- `ui/web`: React + Vite dashboard

## Run with `quodeq dashboard` (recommended)

From the repo root:

```bash
uv run quodeq dashboard
```

Dependencies and the web UI are installed and built automatically on first run. Opens at `http://localhost:4173`.
The dashboard auto-starts (or reuses) the Python Action API and picks an available port starting at 8001.

### Troubleshooting

- If the browser shows `Cannot GET /` and CSP warnings, the UI server is not serving the built `ui/web/dist` assets. Re-run `uv run quodeq dashboard` without `--no-build`, or ensure `ui/web/dist/index.html` exists. The CSP messages are a symptom of the error page, not the UI itself.

Options:

```bash
uv run quodeq dashboard --port 8080        # custom port
uv run quodeq dashboard --open false      # skip auto-opening browser
uv run quodeq dashboard --no-build        # skip web UI build (requires ui/web/dist to exist)
uv run quodeq dashboard --reports <dir>   # custom reports directory
uv run quodeq dashboard --static-dist <dir> # custom ui/web/dist path
uv run quodeq dashboard --repo-root <dir> # custom repo root
```

You can override the Action API host/port used by the dashboard:

```bash
uv run quodeq dashboard --api-host 127.0.0.1 --api-port 8001
```

---

## Run in development

Start the Python Action API:

```bash
uv run python -m quodeq.action_api
```

Then in another terminal:

```bash
cd ui/web
npm install
npm run dev
```

Then open `http://localhost:5173`.

## API endpoints

- `GET /api/projects`
- `GET /api/projects/:project/dashboard?run=latest|<runId>`
- `GET /api/projects/:project/accumulated?asOf=<runId>`
- `GET /api/projects/:project/runs/:runId/dimensions/:dimension/eval`
- `GET /api/projects/:project/runs/:runId/plan`
- `GET /api/projects/:project/runs/:runId/violations`
- `POST /api/evaluations`
- `GET /api/evaluations/:jobId`
- `GET /api/browse`

