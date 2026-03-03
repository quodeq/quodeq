/**
 * Static API registry — describes every endpoint the CodeCompass server exposes.
 * Consumed by the GET /api handler to make the API self-documenting.
 */

export function getRegistry() {
  return [
    {
      method: 'GET',
      path: '/api',
      description: 'Returns this registry — a JSON manifest of every API endpoint.',
      params: { path: null, query: null, body: null },
      dataSource: 'static: registry.js descriptor array',
      response: '{ name, version, endpointCount, endpoints[] }'
    },
    {
      method: 'GET',
      path: '/api/health',
      description: 'Returns a static health-check payload.',
      params: { path: null, query: null, body: null },
      dataSource: 'static: { ok: true }',
      response: '{ ok: true }'
    },
    {
      method: 'GET',
      path: '/api/projects',
      description: 'Lists all evaluated projects by scanning evaluations/ subdirectories.',
      params: { path: null, query: null, body: null },
      dataSource: 'filesystem: evaluations/*/',
      response: '{ projects: [{ name, runsCount, latestRunId, ... }] }'
    },
    {
      method: 'GET',
      path: '/api/projects/:project/info',
      description: 'Returns stored repository metadata for a project.',
      params: {
        path: { project: 'Project name (directory under evaluations/)' },
        query: null,
        body: null
      },
      dataSource: 'filesystem: evaluations/<project>/repository_info.json',
      response: '{ url, defaultBranch, ... } (contents of repository_info.json)'
    },
    {
      method: 'GET',
      path: '/api/projects/:project/dashboard',
      description: 'Builds the full dashboard for a project run, including summary, dimensions, violations, compliance, and trend.',
      params: {
        path: { project: 'Project name (directory under evaluations/)' },
        query: { run: 'Run ID (YYYYMMDD). Defaults to "latest"' },
        body: null
      },
      dataSource: 'filesystem: evaluations/<project>/<runId>/evaluation/*.md|.json + evidence/*.json',
      response: '{ project, availableRuns, selectedRun, summary, trend, dimensions, ... }'
    },
    {
      method: 'GET',
      path: '/api/projects/:project/accumulated',
      description: 'Accumulates evaluation data across all runs for a project, optionally filtered by date.',
      params: {
        path: { project: 'Project name (directory under evaluations/)' },
        query: { asOf: 'Optional cutoff date. Only runs up to this date are included' },
        body: null
      },
      dataSource: 'filesystem: evaluations/<project>/*/',
      response: '{ project, runs, accumulated, ... }'
    },
    {
      method: 'GET',
      path: '/api/projects/:project/runs/:runId/dimensions/:dimension/eval',
      description: 'Returns the parsed evaluation file for a single dimension within a run. Tries JSON, then markdown, then evidence, then live stream.',
      params: {
        path: {
          project: 'Project name',
          runId: 'Run ID (YYYYMMDD)',
          dimension: 'Dimension slug (e.g. maintainability)'
        },
        query: null,
        body: null
      },
      dataSource: 'filesystem: evaluations/<project>/<runId>/evaluation/<dimension>.json|.md + evidence/<dimension>.json',
      response: '{ dimension, content, format, ... }'
    },
    {
      method: 'GET',
      path: '/api/projects/:project/runs/:runId/violations',
      description: 'Returns an aggregated violation summary for a specific run, derived from the dashboard build.',
      params: {
        path: {
          project: 'Project name',
          runId: 'Run ID (YYYYMMDD)'
        },
        query: null,
        body: null
      },
      dataSource: 'derived: buildDashboard() → violation aggregation',
      response: '{ total, critical, major, minor, files: [{ path, count, ... }] }'
    },
    {
      method: 'POST',
      path: '/api/evaluations',
      description: 'Starts a new evaluation job by spawning the codecompass CLI.',
      params: {
        path: null,
        query: null,
        body: {
          repo: 'Repository URL or path (required)',
          dimensions: 'Comma-separated dimension slugs to evaluate',
          numerical: 'Whether to include numerical scoring',
          discipline: 'Evaluation discipline/profile'
        }
      },
      dataSource: 'process: spawns codecompass evaluate CLI',
      response: '{ jobId, status, ... } (HTTP 202)'
    },
    {
      method: 'GET',
      path: '/api/evaluations/:jobId',
      description: 'Returns the current status and logs for an evaluation job.',
      params: {
        path: { jobId: 'Job ID returned by POST /api/evaluations' },
        query: null,
        body: null
      },
      dataSource: 'in-memory: job manager store',
      response: '{ jobId, status, logs, outputProject, outputRunId, ... }'
    },
    {
      method: 'GET',
      path: '/api/browse',
      description: 'Lists directories at a given filesystem path for the repository browser.',
      params: {
        path: null,
        query: { path: 'Filesystem path to list. Defaults to user home directory' },
        body: null
      },
      dataSource: 'filesystem: directory listing at requested path',
      response: '{ current, parent, directories: [{ name, path, isGitRepo }], isGitRepo }'
    },
    {
      method: 'GET',
      path: '/api/ai-clients',
      description: 'Lists available AI client configurations. Proxied to the Python action API when configured.',
      params: { path: null, query: null, body: null },
      dataSource: 'proxy: action API /api/ai-clients',
      response: '[ { id, name, provider, ... } ]'
    },
    {
      method: 'GET',
      path: '/api/ai-clients/:clientId/models',
      description: 'Lists models available for a specific AI client. Proxied to the Python action API when configured.',
      params: {
        path: { clientId: 'AI client identifier' },
        query: null,
        body: null
      },
      dataSource: 'proxy: action API /api/ai-clients/:clientId/models',
      response: '[ { id, name, ... } ]'
    }
  ];
}
