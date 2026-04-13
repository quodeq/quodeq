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

export { listDismissedFindings, dismissFinding, restoreFinding, restoreAllFindings, getRescore } from './findings.js';
export { listStandards, getStandard, createStandard, updateStandard, deleteStandard, duplicateStandard, listLibrary, listCwes, importFromLibrary, importStandard, exportStandard } from './standards.js';

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

/** @returns {Promise<import('../models/job.js').Job[]>} */
export async function listEvaluations({ limit } = {}) {
  const params = limit ? `?limit=${limit}` : '';
  const data = await request(`/evaluations${params}`);
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

export function getOllamaStatus() {
  return request('/ollama/status');
}

export async function getOllamaModels() {
  const data = await request('/ollama/models');
  return data?.models ?? [];
}

export function testOllamaConcurrency(model) {
  return request('/ollama/test-concurrency', {
    method: 'POST',
    body: JSON.stringify({ model }),
  });
}

export function testProviderConnection({ apiBase, model, apiKey }) {
  return request('/provider/test', {
    method: 'POST',
    body: JSON.stringify({ api_base: apiBase, model, api_key: apiKey }),
  });
}

export function getKnownModels() {
  return request('/known-models');
}

export function getProviderConfigs() {
  return request('/provider-configs');
}

export function scanPath(dirPath) {
  return request('/scan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: dirPath }) });
}

// Standards and findings APIs are re-exported at the top of this file.
