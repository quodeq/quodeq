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
import { createDimension, createDimensionEval, createSlimDimension } from '../models/dimension.js';
import { createJob } from '../models/job.js';
import { createProject } from '../models/project.js';
import { request, BASE } from './request.js';

export { listDismissedFindings, dismissFinding, restoreFinding, restoreAllFindings, getRescore, deleteFinding, deleteAllFindings, listVerifiedFindings, unverifyFinding } from './findings.js';
export { listStandards, getStandard, createStandard, updateStandard, deleteStandard, duplicateStandard, listLibrary, listCwes, importFromLibrary, importStandard, exportStandard, getStandardsOverrides, putStandardsOverrides } from './standards.js';
export {
  createAssistantSession, fetchAssistantWorkspace, postAssistantMessage, stopAssistantTurn,
  applyAssistantAction, rejectAssistantAction, assistantEventsUrl,
} from './assistant.js';
export {
  getSharedStatus, connectShared, disconnectShared, refreshShared,
  sharedListProjects, sharedGetProjectInfo, sharedGetRuns,
  sharedGetDashboard, sharedGetAccumulated, sharedGetProjectScores,
  sharedGetRunScores, sharedGetDimensionEval, sharedGetViolations,
  sharedListDismissedFindings, sharedListVerifiedFindings,
  publishProject, pullSharedProject,
} from './shared.js';
export { listTerminalSessions, createTerminalSession, killTerminalSession } from './terminal.js';

// ── Health ──────────────────────────────────────────────────────────────

export function getHealth() {
  return request('/health');
}

// ── Projects ────────────────────────────────────────────────────────────

// First startup after an upgrade can invalidate the backend's score caches,
// making the first /projects response take minutes, not seconds. The default
// 30s abort turned that into an abandon-and-re-request loop that multiplied
// the backend's recompute; the server single-flights the build now, and this
// wider window lets one request wait it out instead of churning.
const PROJECTS_LIST_TIMEOUT_MS = 120000;

/** @returns {Promise<{ projects: import('../models/project.js').Project[], warmup: object | null }>} */
export async function listProjects() {
  const data = await request('/projects', { timeout: PROJECTS_LIST_TIMEOUT_MS });
  const list = data?.projects ?? data ?? [];
  return {
    projects: Array.isArray(list) ? list.map(createProject) : [],
    warmup: (data && !Array.isArray(data) && data.warmup) || null,
  };
}

/** @returns {Promise<import('../models/project.js').Project>} */
export async function getProjectInfo(projectId) {
  const data = await request(`/projects/${encodeURIComponent(projectId)}/info`);
  return createProject(data);
}

/**
 * Scan summary for a registered project (file counts, languages, branches).
 *
 * `signal` lets a caller cap the wait with its own AbortSignal (e.g.
 * `AbortSignal.timeout(...)`); pass a matching `timeout` alongside it when
 * the cap exceeds request()'s 30s default, or the internal timer aborts
 * first. Rejects on any non-2xx response, like every other adapter call.
 *
 * @param {string} projectId
 * @param {{ signal?: AbortSignal, timeout?: number }} [options]
 * @returns {Promise<Object>} raw scan payload
 */
export function getProjectScan(projectId, { signal, timeout } = {}) {
  return request(`/projects/${encodeURIComponent(projectId)}/scan`, { signal, timeout });
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
  const data = await request(`/projects/${encodeURIComponent(projectId)}/scores${q}`);
  if (data?.accumulated && Array.isArray(data.accumulated.dimensions)) {
    data.accumulated.dimensions = data.accumulated.dimensions.map(createDimension);
  }
  return data;
}

/** @returns {Promise<{dimensions: Array, summary: Object}>} */
export async function getRunScores(projectId, runId) {
  const data = await request(`/projects/${encodeURIComponent(projectId)}/scores/${encodeURIComponent(runId)}`);
  if (Array.isArray(data?.dimensions)) data.dimensions = data.dimensions.map(createSlimDimension);
  return data;
}

/**
 * Slim scores payload for the Compare tab: accumulated summary + dimensions
 * (findings stripped server-side) + trend. One call per project.
 *
 * @returns {Promise<{project: string, summary: Object, dimensions: Array, trend: Array, runsCount: number, lastRun: Object|null}>}
 */
export async function getCompareSummary(projectId) {
  const data = await request(`/projects/${encodeURIComponent(projectId)}/compare-summary`);
  if (Array.isArray(data?.dimensions)) data.dimensions = data.dimensions.map(createSlimDimension);
  return data;
}

// ── Grade formula ───────────────────────────────────────────────────────

/** @returns {Promise<{current: Object, defaults: Object, isCustom: boolean}>} */
export function getGradeFormula() {
  return request('/grade-formula');
}

/** @returns {Promise<{current: Object, defaults: Object, isCustom: boolean, applied: number}>} */
export function saveGradeFormula(params) {
  return request('/grade-formula', { method: 'PUT', body: JSON.stringify(params) });
}

/** @returns {Promise<{current: Object, defaults: Object, isCustom: boolean, applied: number}>} */
export function resetGradeFormula() {
  return request('/grade-formula', { method: 'DELETE' });
}

/** @returns {Promise<{project: string, runId: string, before: Object, after: Object}>} */
export function previewGradeFormula(projectId, params) {
  return request('/grade-formula/preview', {
    method: 'POST',
    body: JSON.stringify({ project: projectId, params }),
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
 * Cancel a running evaluation. Declares intent=cancel so the server can
 * never route this to the permanent-purge branch, even if the run finished
 * while the confirm dialog was open (it 409s instead and the run is kept).
 * @param {string} jobId
 * @param {{discard?: boolean}} [opts]
 * @returns {Promise<Object>}
 */
export function cancelEvaluation(jobId, opts = {}) {
  const qs = opts.discard ? '?intent=cancel&discard=true' : '?intent=cancel';
  // The server-side cancel path can block for the full SIGTERM grace window
  // (~30s) plus the terminal-status wait before responding; the default 30s
  // request timeout aborted client-side right before the backend finished.
  return request(`/evaluations/${encodeURIComponent(jobId)}${qs}`, { method: 'DELETE', timeout: 45000 });
}

/**
 * Permanently delete a non-running evaluation from history (removes scan
 * dir + index row). Declares intent=delete so a run that is unexpectedly
 * still running is refused (409) instead of being silently cancelled.
 * @param {string} jobId
 * @returns {Promise<Object>}
 */
export function deleteEvaluation(jobId) {
  return request(`/evaluations/${encodeURIComponent(jobId)}?intent=delete`, { method: 'DELETE' });
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

/** @returns {Promise<Object>} Whether a llama.cpp log file is configured on the server */
export function getLlamacppLogAvailable() {
  return request('/llamacpp/logs/available');
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

/** @returns {Promise<Object>} omlx connection status */
export function getOmlxStatus(baseUrl) {
  const params = baseUrl ? `?base_url=${encodeURIComponent(baseUrl)}` : '';
  return request(`/omlx/status${params}`);
}

/** @returns {Promise<Object[]>} Available omlx models */
export async function getOmlxModels(baseUrl, apiKey) {
  const params = new URLSearchParams();
  if (baseUrl) params.set('base_url', baseUrl);
  const qs = params.toString() ? `?${params}` : '';
  // The API key travels in a header, never the query string: query strings
  // end up in server access logs and browser history.
  const options = apiKey ? { headers: { 'X-Api-Key': apiKey } } : {};
  const data = await request(`/omlx/models${qs}`, options);
  return data?.models ?? [];
}

/** @returns {Promise<Object>} Concurrency test results for the given model */
export function testOmlxConcurrency(model, baseUrl, apiKey) {
  return request('/omlx/test-concurrency', {
    method: 'POST',
    body: JSON.stringify({ model, base_url: baseUrl || undefined, api_key: apiKey || undefined }),
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

// --- Update notifications ---

export function getUpdateStatus() {
  return request('/update/status');
}

export function checkForUpdates() {
  return request('/update/check', { method: 'POST' });
}

export function dismissUpdate(version) {
  return request('/update/dismiss', { method: 'POST', body: JSON.stringify({ version }) });
}

export function setUpdateAutoCheck(enabled) {
  return request('/update/settings', { method: 'POST', body: JSON.stringify({ auto_check_enabled: enabled }) });
}

export function markUpdateDisclosed() {
  return request('/update/settings', { method: 'POST', body: JSON.stringify({ disclosed: true }) });
}
/**
 * Register a new project without starting an evaluation.
 * Used by the onboarding wizard's Repo & Scan step.
 *
 * @param {{ repo: string, cloneDest?: string, ephemeral?: boolean, branch?: string, scopePath?: string, discipline?: string }} payload
 * @returns {Promise<{ projectId: string, scanData: object }>}
 * @throws {Error & { status: number, code?: string, existingProjectId?: string }} on non-2xx
 */
export async function registerProject(payload) {
  let res;
  try {
    res = await fetch('/api/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      // Generous: registration may clone a large repository server-side,
      // but a hung backend must not leave onboarding pending forever.
      signal: AbortSignal.timeout(600000), // 10 min
    });
  } catch (e) {
    if (e?.name === 'TimeoutError' || e?.name === 'AbortError') {
      throw new Error('Project registration timed out. The server may be unresponsive or the clone is taking too long; try again.');
    }
    throw e;
  }
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
