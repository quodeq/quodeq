/**
 * API client / repository layer.
 *
 * Every public function maps a raw JSON response to a typed model object
 * (see ../models/) so components never see raw API shapes.
 *
 * Standards and findings APIs are in separate modules; re-exported here
 * for backward compatibility.
 */

import { createDashboard } from '../models/dashboard.js';
import { createDimension, createDimensionEval } from '../models/dimension.js';
import { createJob } from '../models/job.js';
import { createProject } from '../models/project.js';
import { request, BASE } from './request.js';

export { listDismissedFindings, dismissFinding, restoreFinding, restoreAllFindings, getRescore, deleteFinding, deleteAllFindings } from './findings.js';
export { listStandards, getStandard, createStandard, updateStandard, deleteStandard, duplicateStandard, listLibrary, listCwes, importFromLibrary, importStandard, exportStandard } from './standards.js';
export { listVerifications } from '../tabs/verifier/api.js';

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

// ── Unified Scores ─────────────────────────────────────────────────────

/** @returns {Promise<{accumulated: Object, trend: Array, availableRuns: Array}>} */
export async function getProjectScores(projectId, asOfRun = null) {
  const q = asOfRun ? `?asOf=${encodeURIComponent(asOfRun)}` : '';
  return request(`/projects/${encodeURIComponent(projectId)}/scores${q}`);
}

/** @returns {Promise<{dimensions: Array, summary: Object}>} */
export async function getRunScores(projectId, runId) {
  return request(`/projects/${encodeURIComponent(projectId)}/scores/${encodeURIComponent(runId)}`);
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
  const data = await request(`/projects/${encodeURIComponent(projectId)}/accumulated${q}`);
  if (data && Array.isArray(data.dimensions)) {
    data.dimensions = data.dimensions.map(createDimension);
  }
  return data;
}

// ── Evaluations / Jobs ──────────────────────────────────────────────────

/**
 * @param {{ limit?: number, states?: string[] }} [options]
 * @returns {Promise<import('../models/job.js').Job[]>}
 */
export async function listEvaluations({ limit, states } = {}) {
  const params = new URLSearchParams();
  if (limit) params.set('limit', String(limit));
  if (states && states.length) params.set('state', states.join(','));
  const qs = params.toString();
  const data = await request(`/evaluations${qs ? `?${qs}` : ''}`);
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
 * Live progress for a scan. Pure on-disk read — works for internal and
 * external (CLI-started) runs uniformly.
 * @param {string} jobId
 * @returns {Promise<Object>}
 */
export function getEvaluationProgress(jobId) {
  return request(`/evaluations/${encodeURIComponent(jobId)}/progress`);
}

/**
 * @param {string} jobId
 * @param {{discard?: boolean}} [opts]
 * @returns {Promise<Object>}
 */
export function cancelEvaluation(jobId, opts = {}) {
  const qs = opts.discard ? '?discard=true' : '';
  return request(`/evaluations/${encodeURIComponent(jobId)}${qs}`, { method: 'DELETE' });
}

/**
 * Permanently delete a non-running evaluation from history (removes scan dir + index row).
 * The server DELETE endpoint routes running jobs to cancel and finished jobs to purge —
 * this helper is the semantic alias UI callers use when they want the purge path.
 * @param {string} jobId
 * @returns {Promise<Object>}
 */
export function deleteEvaluation(jobId) {
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
 * @param {{ files?: boolean }} [options]
 * @returns {Promise<{ current: string, parent: string|null, directories: Object[], files?: Object[] }>}
 */
export function browseDirectory(dirPath = '', options = {}) {
  const params = new URLSearchParams();
  if (dirPath) params.set('path', dirPath);
  if (options.files) params.set('files', '1');
  const q = params.toString() ? `?${params}` : '';
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

// ── LLM Bridge ─────────────────────────────────────────────────────────

/** @returns {Promise<Object>} Ollama connection status */
export function getOllamaStatus() {
  return request('/ollama/status');
}

/** @returns {Promise<Object[]>} Available Ollama models */
export async function getOllamaModels() {
  const data = await request('/ollama/models');
  return data?.models ?? [];
}

/** @returns {Promise<Object>} Concurrency test results for the given model */
export function testOllamaConcurrency(model) {
  return request('/ollama/test-concurrency', {
    method: 'POST',
    body: JSON.stringify({ model }),
  });
}

/** @returns {Promise<Object>} llama.cpp connection status */
export function getLlamacppStatus() {
  return request('/llamacpp/status');
}

/** @returns {Promise<Object[]>} Loaded llama.cpp model (0 or 1 entries) */
export async function getLlamacppModels() {
  const data = await request('/llamacpp/models');
  return data?.models ?? [];
}

/** @returns {Promise<Object>} Concurrency test results for the loaded model */
export function testLlamacppConcurrency(model) {
  return request('/llamacpp/test-concurrency', {
    method: 'POST',
    body: JSON.stringify({ model: model || '' }),
  });
}

/** @returns {Promise<Object>} Connection test result for the provider */
export function testProviderConnection({ provider, apiBase, model, apiKey }) {
  return request('/provider/test', {
    method: 'POST',
    body: JSON.stringify({ provider, api_base: apiBase, model, api_key: apiKey }),
  });
}

/** @returns {Promise<Object[]>} Known model definitions */
export function getKnownModels() {
  return request('/known-models');
}

/** @returns {Promise<Object[]>} Saved provider configurations */
export function getProviderConfigs() {
  return request('/provider-configs');
}

/** @returns {Promise<Object>} Scan results for the given directory path */
export function scanPath(dirPath) {
  return request('/scan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: dirPath }) });
}

// Standards and findings APIs are re-exported at the top of this file.

/**
 * Import a previously-exported project zip.
 *
 * Uses raw fetch so we can (a) send multipart/form-data without the shared
 * request() wrapper forcing application/json, and (b) read err.status,
 * err.kind, err.existingProjectId on a 409 collision so the caller can
 * prompt the user to choose Replace / Import as copy / Cancel.
 *
 * @param {File|Blob} file - the .zip file to import
 * @param {{ action?: 'replace'|'copy' }} [opts]
 * @returns {Promise<{ imported: boolean, projectId: string, sourceProjectId: string, renamed: boolean, projectName?: string }>}
 * @throws {Error & { status: number, code?: string, kind?: string, existingProjectId?: string, projectName?: string }} on non-2xx
 */
export async function importProject(file, opts = {}) {
  const form = new FormData();
  form.append('file', file);
  if (opts.action) form.append('action', opts.action);
  // No timeout: large project zips can take a while to upload.
  const res = await fetch(`${BASE}/projects/import`, { method: 'POST', body: form });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(body.error || `importProject failed (${res.status})`);
    err.status = res.status;
    if (body.code) err.code = body.code;
    if (body.kind) err.kind = body.kind;
    if (body.existingProjectId) err.existingProjectId = body.existingProjectId;
    if (body.projectName) err.projectName = body.projectName;
    throw err;
  }
  return body;
}

// Note: uses raw fetch (not the shared request() wrapper) so the wizard can
// read err.status and err.existingProjectId on a 409 duplicate response —
// request() throws plain Error and discards both. Refactoring request() to
// enrich errors is a separate concern.
/**
 * Register a new project without starting an evaluation.
 * Used by the onboarding wizard's Repo & Scan step.
 *
 * @param {{ repo: string, cloneDest?: string, ephemeral?: boolean, branch?: string, scopePath?: string, discipline?: string }} payload
 * @returns {Promise<{ projectId: string, scanData: object }>}
 * @throws {Error & { status: number, code?: string, existingProjectId?: string }} on non-2xx
 */
export async function registerProject(payload) {
  const res = await fetch('/api/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(body.error || `registerProject failed (${res.status})`);
    err.status = res.status;
    if (body.code) err.code = body.code;
    if (body.existingProjectId) err.existingProjectId = body.existingProjectId;
    throw err;
  }
  return body;
}
