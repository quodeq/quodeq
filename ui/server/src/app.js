import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import express from 'express';
import cors from 'cors';
import { createJobManager } from './jobs/evaluationJobs.js';
import { createProjectsRouter } from './routes/projects.js';
import { createEvaluationsRouter } from './routes/evaluations.js';
import { createBrowseRouter } from './routes/browse.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const defaultRepoRoot = path.resolve(__dirname, '../../..');
const defaultReportsRoot = path.resolve(defaultRepoRoot, 'evaluations');

function resolveEvaluateCommand(repoRoot) {
  const venvCommand = path.resolve(repoRoot, '.venv', 'bin', 'codecompass');
  if (fs.existsSync(venvCommand)) {
    return [venvCommand, 'evaluate'];
  }
  return ['uv', 'run', 'codecompass', 'evaluate'];
}

function parseCommand(value) {
  if (!value) return null;
  return String(value).trim().split(/\s+/).filter(Boolean);
}

export async function proxyToActionApi(req, res, actionApiBase) {
  try {
    const url = `${actionApiBase}${req.originalUrl}`;
    const headers = { 'Content-Type': 'application/json' };
    const fetchOptions = { method: req.method, headers };
    if (req.method !== 'GET' && req.method !== 'HEAD') {
      fetchOptions.body = JSON.stringify(req.body ?? {});
    }
    const response = await fetch(url, fetchOptions);
    const contentType = response.headers.get('content-type') || 'application/json';
    const isBinary = !contentType.startsWith('text/') && !contentType.includes('json');
    const body = isBinary ? Buffer.from(await response.arrayBuffer()) : await response.text();
    res.status(response.status);
    res.set('content-type', contentType);
    if (response.headers.has('content-disposition')) {
      res.set('content-disposition', response.headers.get('content-disposition'));
    }
    res.send(body);
  } catch (error) {
    res.status(502).json({ error: error.message || 'Failed to reach action API' });
  }
}

export function createApp(options = {}) {
  const app = express();

  const reportsRoot = options.reportsRoot ?? defaultReportsRoot;
  const repoRoot = options.repoRoot ?? defaultRepoRoot;
  const staticDistPath = options.staticDistPath ?? options.staticDist ?? null;
  const actionApiBase = options.actionApiBase ?? process.env.CODECOMPASS_ACTION_API ?? null;

  const evaluateCommand =
    options.evaluateCommand ??
    parseCommand(process.env.CODECOMPASS_EVALUATE_CMD) ??
    resolveEvaluateCommand(repoRoot);

  const jobManager =
    options.jobManager ??
    createJobManager({ repoRoot, reportsRoot, evaluateCommand });

  app.use(cors());
  app.use(express.json({ limit: '1mb' }));

  if (actionApiBase) {
    app.use('/api', (req, res) => proxyToActionApi(req, res, actionApiBase));
  } else {
    app.get('/api/projects/:project/info', (req, res) => {
      try {
        const infoPath = path.join(reportsRoot, req.params.project, 'repository_info.json');
        const info = JSON.parse(fs.readFileSync(infoPath, 'utf-8'));
        res.json(info);
      } catch {
        res.status(404).json({ error: 'Repository info not found' });
      }
    });

    app.get('/api/health', (_req, res) => {
      res.json({ ok: true });
    });

    app.use('/api', createProjectsRouter({ reportsRoot }));
    app.use('/api', createEvaluationsRouter({ jobManager }));
    app.use('/api', createBrowseRouter());
  }

  if (staticDistPath) {
    app.use(express.static(staticDistPath));
    app.get('*', (req, res, next) => {
      if (req.path.startsWith('/api/')) {
        return next();
      }
      const indexFile = path.join(staticDistPath, 'index.html');
      if (fs.existsSync(indexFile)) {
        res.sendFile(indexFile);
      } else {
        next();
      }
    });
  }

  return app;
}
