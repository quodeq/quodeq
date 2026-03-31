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

export function deleteProject(projectId) {
  return request(`/projects/${encodeURIComponent(projectId)}?confirm=true`, { method: 'DELETE' });
}

export function getProjectExportUrl(projectId) {
  return `${BASE}/projects/${encodeURIComponent(projectId)}/export`;
}

export function relocateProject(projectId, newPath) {
  return request(`/projects/${encodeURIComponent(projectId)}/path`, {
    method: 'PATCH',
    body: JSON.stringify({ path: newPath }),
  });
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

// ── Standards ──────────────────────────────────────────────
export async function listStandards() {
  return request('/standards');
}
export async function getStandard(standardId) {
  return request(`/standards/${encodeURIComponent(standardId)}`);
}
export async function createStandard(data) {
  return request('/standards', { method: 'POST', body: JSON.stringify(data) });
}
export async function updateStandard(standardId, data) {
  return request(`/standards/${encodeURIComponent(standardId)}`, { method: 'PUT', body: JSON.stringify(data) });
}
export async function deleteStandard(standardId) {
  return request(`/standards/${encodeURIComponent(standardId)}`, { method: 'DELETE' });
}
export async function duplicateStandard(standardId, newId) {
  return request(`/standards/${encodeURIComponent(standardId)}/duplicate`, { method: 'POST', body: JSON.stringify({ newId }) });
}
export async function listLibrary() {
  return request('/standards/library');
}
export async function listCwes() {
  return request('/standards/refs/cwe');
}
export async function importFromLibrary(file) {
  return request('/standards/library/import', { method: 'POST', body: JSON.stringify({ file }) });
}
export async function importStandard(data, force = false) {
  const BASE = import.meta.env.VITE_API_BASE || '/api';
  const res = await fetch(`${BASE}/standards/import`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ data, force }),
  });
  const body = await res.json().catch(() => ({}));
  if (res.status === 409) return { ...body, _conflict: true };
  if (!res.ok) throw new Error(body.error || `Import failed: ${res.status}`);
  return body;
}
export async function downloadStandard(standardId) {
  const detail = await getStandard(standardId);
  const { managed, type, origin, originHash, principleCount, requirementCount, ...portable } = detail;
  const blob = new Blob([JSON.stringify(portable, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${standardId}.quodeq`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
