import { randomUUID } from 'node:crypto';
import { spawn } from 'node:child_process';

const LOG_CAP = 600;

const DEFAULT_CMD_BASE = ['uv', 'run', 'codecompass', 'evaluate'];
const REPORT_PATH_RE = /Report path:.*[/\\]([^/\\\s]+)[/\\]([^/\\\s]+)[/\\]evaluation/;

function parseDimensions(raw) {
  if (!raw) return [];
  if (Array.isArray(raw)) {
    return raw.map((d) => String(d).trim()).filter(Boolean);
  }
  return String(raw).split(',').map((d) => d.trim()).filter(Boolean);
}

function buildArgs(payload, reportsRoot) {
  const result = [];
  const dims = parseDimensions(payload.dimensions);

  if (dims.length > 0) {
    result.push('-d', dims.join(','));
  }
  if (payload.numerical) {
    result.push('-n');
  }
  if (reportsRoot) {
    result.push('--evaluations', String(reportsRoot));
  }
  if (payload.discipline && String(payload.discipline).trim()) {
    result.push(String(payload.discipline).trim());
  }
  result.push(String(payload.repo).trim());
  return result;
}

function ingestChunk(record, raw) {
  const text = typeof raw === 'string' ? raw : raw.toString();
  const lines = text.split(/\r?\n/).filter((l) => l.length > 0);
  record.logs.push(...lines);
  if (record.logs.length > LOG_CAP) {
    record.logs = record.logs.slice(record.logs.length - LOG_CAP);
  }
}

function tryExtractReportPath(record, raw) {
  const text = typeof raw === 'string' ? raw : raw.toString();
  const m = text.match(REPORT_PATH_RE);
  if (m) {
    record.outputProject = m[1];
    record.outputRunId = m[2];
  }
}

function snapshot(record) {
  return { ...record, logs: record.logs.slice() };
}

export function createJobManager({ repoRoot, reportsRoot, evaluateCommand, spawnImpl = spawn } = {}) {
  const registry = new Map();
  let activeId = null;

  const cmdBase = Array.isArray(evaluateCommand) && evaluateCommand.length
    ? [...evaluateCommand]
    : [...DEFAULT_CMD_BASE];

  function getJob(jobId) {
    const rec = registry.get(jobId);
    return rec ? snapshot(rec) : null;
  }

  function startJob(payload) {
    if (!payload || !payload.repo || !String(payload.repo).trim()) {
      const err = new Error('Repository is required');
      err.code = 'INVALID_INPUT';
      throw err;
    }

    if (activeId) {
      const active = registry.get(activeId);
      if (active && active.status === 'running') {
        const err = new Error('An evaluation job is already running');
        err.code = 'JOB_RUNNING';
        throw err;
      }
    }

    const jobId = randomUUID();
    const extraArgs = buildArgs(payload, reportsRoot);
    const fullCmd = [...cmdBase, ...extraArgs];

    const record = {
      jobId,
      status: 'running',
      args: extraArgs,
      command: fullCmd.join(' '),
      startedAt: new Date().toISOString(),
      endedAt: null,
      exitCode: null,
      outputProject: null,
      outputRunId: null,
      logs: []
    };

    registry.set(jobId, record);
    activeId = jobId;

    const proc = spawnImpl(fullCmd[0], fullCmd.slice(1), {
      cwd: repoRoot,
      env: process.env
    });

    proc.stdout?.on('data', (chunk) => {
      ingestChunk(record, chunk);
      tryExtractReportPath(record, chunk);
    });

    proc.stderr?.on('data', (chunk) => {
      ingestChunk(record, chunk);
      tryExtractReportPath(record, chunk);
    });

    proc.on('error', (err) => {
      ingestChunk(record, `PROCESS ERROR: ${err.message}`);
      record.status = 'failed';
      record.exitCode = -1;
      record.endedAt = new Date().toISOString();
      if (activeId === jobId) activeId = null;
    });

    proc.on('close', (code) => {
      record.exitCode = code;
      record.status = code === 0 ? 'completed' : 'failed';
      record.endedAt = new Date().toISOString();
      if (activeId === jobId) activeId = null;
    });

    return getJob(jobId);
  }

  return { startJob, getJob };
}
