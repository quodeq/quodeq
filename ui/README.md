# CodeCompass UI Dashboard

Local dashboard for analyzed projects under `reports/`.

## Structure

- `ui/server`: Express gateway that forwards UI requests to the Python Action API
- `ui/web`: React + Vite dashboard

## Run with `codecompass dashboard` (recommended)

From the repo root:

```bash
uv run codecompass dashboard
```

Dependencies and the web UI are installed and built automatically on first run. Opens at `http://localhost:4173`.
The dashboard auto-starts (or reuses) the Python Action API and picks an available port starting at 8001.

### Troubleshooting

- If the browser shows `Cannot GET /` and CSP warnings, the UI server is not serving the built `ui/web/dist` assets. Re-run `uv run codecompass dashboard` without `--no-build`, or ensure `ui/web/dist/index.html` exists. The CSP messages are a symptom of the error page, not the UI itself.

Options:

```bash
uv run codecompass dashboard --port 8080        # custom port
uv run codecompass dashboard --open false      # skip auto-opening browser
uv run codecompass dashboard --no-build        # skip web UI build (requires ui/web/dist to exist)
uv run codecompass dashboard --reports <dir>   # custom reports directory
uv run codecompass dashboard --static-dist <dir> # custom ui/web/dist path
uv run codecompass dashboard --repo-root <dir> # custom repo root
```

You can override the Action API host/port used by the dashboard:

```bash
uv run codecompass dashboard --api-host 127.0.0.1 --api-port 8001
```

---

## Run in development

Start the Python Action API:

```bash
uv run python -m codecompass.action_api
```

Then in one terminal:

```bash
cd ui/server
npm install
CODECOMPASS_ACTION_API=http://127.0.0.1:8001 npm run dev
```

In another terminal:

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

## Evaluation command override

The UI server can still run evaluations directly when no Action API is configured. You can override the command:

```bash
export CODECOMPASS_EVALUATE_CMD="uv run codecompass evaluate"
```
