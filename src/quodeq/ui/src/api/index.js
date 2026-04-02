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

/**
 * @param {string} projectId
 * @returns {Promise<Object>}
 */
export function deleteProject(projectId) {
  return request(`/projects/${encodeURIComponent(projectId)}?confirm=true`, { method: 'DELETE' });
}

/**
 * @param {string} projectId
 * @returns {string} Download URL for the project export
 */
export function getProjectExportUrl(projectId) {
  return `${BASE}/projects/${encodeURIComponent(projectId)}/export`;
}

/**
 * @param {string} projectId
 * @param {string} newPath
 * @returns {Promise<Object>}
 */
export function relocateProject(projectId, newPath) {
  return request(`/projects/${encodeURIComponent(projectId)}/path`, {
    method: 'PATCH',
    body: JSON.stringify({ path: newPath }),
  });
}

/**
 * @param {string} projectId
 * @param {string} destination
 * @returns {Promise<Object>}
 */
export function cloneToLocal(projectId, destination) {
  return request(`/projects/${encodeURIComponent(projectId)}/clone-local`, {
    method: 'POST',
    body: JSON.stringify({ destination }),
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

/**
 * @param {string} jobId
 * @returns {Promise<Object>}
 */
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

/**
 * @param {string} [dirPath='']
 * @returns {Promise<{ current: string, parent: string|null, directories: Object[] }>}
 */
export function browseDirectory(dirPath = '') {
  const q = dirPath ? `?path=${encodeURIComponent(dirPath)}` : '';
  return request(`/browse${q}`);
}

/**
 * @param {string} path - Parent directory path
 * @param {string} name - New directory name
 * @returns {Promise<Object>}
 */
export function createDirectory(path, name) {
  return request('/browse/mkdir', {
    method: 'POST',
    body: JSON.stringify({ path, name }),
  });
}

/** @returns {Promise<Object[]>} */
export function listPlugins() {
  return request('/plugins');
}

/** @returns {Promise<Object[]>} */
export function getAiClients() {
  return request('/ai-clients');
}

/**
 * @param {string} clientId
 * @returns {Promise<Object[]>}
 */
export function getClientModels(clientId) {
  return request(`/ai-clients/${encodeURIComponent(clientId)}/models`);
}

// ── Standards ──────────────────────────────────────────────
/** @returns {Promise<Object[]>} */
export async function listStandards() {
  return request('/standards');
}
/**
 * @param {string} standardId
 * @returns {Promise<Object>}
 */
export async function getStandard(standardId) {
  return request(`/standards/${encodeURIComponent(standardId)}`);
}
/**
 * @param {Object} data - Standard definition
 * @returns {Promise<Object>}
 */
export async function createStandard(data) {
  return request('/standards', { method: 'POST', body: JSON.stringify(data) });
}
/**
 * @param {string} standardId
 * @param {Object} data - Updated standard definition
 * @returns {Promise<Object>}
 */
export async function updateStandard(standardId, data) {
  return request(`/standards/${encodeURIComponent(standardId)}`, { method: 'PUT', body: JSON.stringify(data) });
}
/**
 * @param {string} standardId
 * @returns {Promise<Object>}
 */
export async function deleteStandard(standardId) {
  return request(`/standards/${encodeURIComponent(standardId)}`, { method: 'DELETE' });
}
/**
 * @param {string} standardId
 * @param {string} newId
 * @returns {Promise<Object>}
 */
export async function duplicateStandard(standardId, newId) {
  return request(`/standards/${encodeURIComponent(standardId)}/duplicate`, { method: 'POST', body: JSON.stringify({ newId }) });
}
/** @returns {Promise<Object[]>} */
export async function listLibrary() {
  return request('/standards/library');
}
/** @returns {Promise<Object[]>} */
export async function listCwes() {
  return request('/standards/refs/cwe');
}
/**
 * @param {string} file - Library file identifier
 * @returns {Promise<Object>}
 */
export async function importFromLibrary(file) {
  return request('/standards/library/import', { method: 'POST', body: JSON.stringify({ file }) });
}
/**
 * @param {Object} data - Standard data to import
 * @param {boolean} [force=false] - Overwrite existing standard if true
 * @returns {Promise<Object>} Result with optional `_conflict` flag
 */
export async function importStandard(data, force = false) {
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
/**
 * Fetch a standard and return a portable (non-managed) representation.
 * @param {string} standardId
 * @returns {Promise<{ id: string, data: Object, fileName: string }>}
 */
export async function exportStandard(standardId) {
  const detail = await getStandard(standardId);
  const { managed, type, origin, originHash, principleCount, requirementCount, ...portable } = detail;
  return { id: standardId, data: portable, fileName: `${standardId}.quodeq` };
}

// ── Dismissed Findings ─────────────────────────────────────────────────

/**
 * List dismissed findings for a project.
 * @param {string} projectId - Project identifier
 * @returns {Promise<Array>} Dismissed findings array
 */
export async function listDismissedFindings(projectId) {
  return request(`/findings/dismissed?project=${encodeURIComponent(projectId)}`);
}

/**
 * Dismiss a finding (exclude from scoring).
 * @param {string} projectId - Project identifier
 * @param {object} finding - Finding data: { req, file, line, dimension, severity, reason }
 * @returns {Promise<object>} Server response
 */
export async function dismissFinding(projectId, finding) {
  return request('/findings/dismiss', {
    method: 'POST',
    body: JSON.stringify({ project: projectId, ...finding }),
  });
}

/**
 * Restore a dismissed finding (include in scoring again).
 * @param {string} projectId - Project identifier
 * @param {object} finding - Finding key: { req, file, line }
 * @returns {Promise<object>} Server response
 */
export async function restoreFinding(projectId, finding) {
  return request('/findings/restore', {
    method: 'POST',
    body: JSON.stringify({ project: projectId, ...finding }),
  });
}

/**
 * Rescore a project run with dismissed findings filtered out.
 * @param {string} projectId - Project identifier
 * @param {string} [run='latest'] - Run ID (optional, defaults to latest)
 * @returns {Promise<{dimensions: Array, summary: object}>} Rescored data
 */
export async function getRescore(projectId, run = 'latest') {
  const params = new URLSearchParams({ project: projectId });
  if (run && run !== 'latest') params.set('run', run);
  return request(`/rescore?${params}`);
}
