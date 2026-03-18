/**
 * API client / repository layer.
 *
 * Every public function maps a raw JSON response to a typed model object
 * (see ../models/) so components never see raw API shapes.
 */

import { createDashboard } from '../models/dashboard.js';
import { createDimensionEval } from '../models/dimension.js';
import { createJob } from '../models/job.js';
import { createProject } from '../models/project.js';

const BASE = import.meta.env.VITE_API_BASE || '/api';
const API_TIMEOUT_MS = 30000;

async function request(path, options = {}) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT_MS);
  try {
    const res = await fetch(`${BASE}${path}`, {
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
      },
      ...options,
      signal: controller.signal,
    });

    const payload = await res.json().catch(() => ({}));

    if (!res.ok) {
      throw new Error(payload.error || `Request failed: ${res.status}`);
    }

    return payload;
  } finally {
    clearTimeout(timeoutId);
  }
}

// ── Health ──────────────────────────────────────────────────────────────

export function getHealth() {
  return request('/health');
}

// ── Projects ────────────────────────────────────────────────────────────

/** @returns {Promise<import('../models/project.js').Project[]>} */
export async function listProjects() {
  const data = await request('/projects');
  const list = data?.projects ?? data ?? [];
  return Array.isArray(list) ? list.map(createProject) : [];
}

/** @returns {Promise<import('../models/project.js').Project>} */
export async function getProjectInfo(projectId) {
  const data = await request(`/projects/${encodeURIComponent(projectId)}/info`);
  return createProject(data);
}

// ── Dashboard ───────────────────────────────────────────────────────────

/** @returns {Promise<import('../models/dashboard.js').Dashboard>} */
export async function getDashboard(projectId, run = 'latest') {
  const q = run ? `?run=${encodeURIComponent(run)}` : '';
  const data = await request(`/projects/${encodeURIComponent(projectId)}/dashboard${q}`);
  return createDashboard(data);
}

/** @returns {Promise<Object>} */
export async function getAccumulated(projectId, asOfRun = null) {
  const q = asOfRun ? `?asOf=${encodeURIComponent(asOfRun)}` : '';
  return request(`/projects/${encodeURIComponent(projectId)}/accumulated${q}`);
}

// ── Evaluations / Jobs ──────────────────────────────────────────────────

/** @returns {Promise<import('../models/job.js').Job[]>} */
export async function listEvaluations() {
  const data = await request('/evaluations');
  return (data || []).map(createJob);
}

/** @returns {Promise<import('../models/job.js').Job>} */
export async function startEvaluation(input) {
  const data = await request('/evaluations', {
    method: 'POST',
    body: JSON.stringify(input),
  });
  return createJob(data);
}

/** @returns {Promise<import('../models/job.js').Job>} */
export async function getEvaluation(jobId) {
  const data = await request(`/evaluations/${encodeURIComponent(jobId)}`);
  return createJob(data);
}

export function cancelEvaluation(jobId) {
  return request(`/evaluations/${encodeURIComponent(jobId)}`, { method: 'DELETE' });
}

// ── Dimension Eval ──────────────────────────────────────────────────────

/** @returns {Promise<import('../models/dimension.js').DimensionEval>} */
export async function getDimensionEval(projectId, runId, dimension) {
  const data = await request(
    `/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/dimensions/${encodeURIComponent(dimension)}/eval`
  );
  return createDimensionEval(data);
}

// ── Browse / Plugins / AI Clients ───────────────────────────────────────

export function browseDirectory(dirPath = '') {
  const q = dirPath ? `?path=${encodeURIComponent(dirPath)}` : '';
  return request(`/browse${q}`);
}

export function listPlugins() {
  return request('/plugins');
}

export function getAiClients() {
  return request('/ai-clients');
}

export function getClientModels(clientId) {
  return request(`/ai-clients/${encodeURIComponent(clientId)}/models`);
}
