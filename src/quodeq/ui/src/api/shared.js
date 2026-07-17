/**
 * Shared repository API client — read-only mirrors of the project read endpoints,
 * plus config management (connect, disconnect, refresh, status) and publish/pull.
 */

import { request } from './request.js';
import { createProject } from '../models/project.js';
import { createDashboard } from '../models/dashboard.js';
import { createDimension, createDimensionEval } from '../models/dimension.js';

// ── Config Management ───────────────────────────────────────────────────────

/**
 * Get the shared repository connection status.
 * @returns {Promise<{configured: boolean, url: string|null, lastSynced: string|null, publish: Object}>}
 */
export function getSharedStatus() {
  return request('/shared/status');
}

/**
 * Connect to a shared repository.
 * @param {string} url - Git repository URL
 * @returns {Promise<{configured: boolean, url: string}>}
 */
export function connectShared(url) {
  return request('/shared/config', {
    method: 'PUT',
    body: JSON.stringify({ url }),
  });
}

/**
 * Disconnect from the shared repository.
 * @returns {Promise<{configured: boolean}>}
 */
export function disconnectShared() {
  return request('/shared/config', {
    method: 'DELETE',
  });
}

/**
 * Refresh the shared repository (fetch latest changes).
 * @returns {Promise<{stale: boolean, lastSynced: string}>}
 */
export function refreshShared() {
  return request('/shared/refresh', {
    method: 'POST',
  });
}

// ── Project List & Info ─────────────────────────────────────────────────────

/**
 * List projects from the shared repository.
 * @param {{refresh?: boolean}} [options={}]
 * @returns {Promise<import('../models/project.js').Project[]>}
 */
export async function sharedListProjects({ refresh = false } = {}) {
  const refreshParam = refresh ? '1' : '0';
  const data = await request(`/shared/projects?refresh=${refreshParam}`);
  const list = data?.projects ?? data ?? [];
  const projects = Array.isArray(list) ? list.map(createProject) : [];

  // Pass through shared-specific metadata
  if (Array.isArray(list)) {
    projects.forEach((proj, idx) => {
      if (list[idx]) {
        proj.publishedBy = list[idx].publishedBy ?? null;
        proj.publishedAt = list[idx].publishedAt ?? null;
        proj.source = list[idx].source ?? 'shared';
      }
    });
  }

  return projects;
}

/**
 * Get detailed info for a shared project.
 * @param {string} projectId
 * @returns {Promise<import('../models/project.js').Project>}
 */
export async function sharedGetProjectInfo(projectId) {
  const data = await request(`/shared/projects/${encodeURIComponent(projectId)}/info`);
  return createProject(data);
}

/**
 * Get runs for a shared project.
 * @param {string} projectId
 * @returns {Promise<{runs: Array}>}
 */
export function sharedGetRuns(projectId) {
  return request(`/shared/projects/${encodeURIComponent(projectId)}/runs`);
}

// ── Dashboard & Scores ──────────────────────────────────────────────────────

/**
 * Get dashboard for a shared project run.
 * @param {string} projectId
 * @param {string} [run='latest']
 * @returns {Promise<import('../models/dashboard.js').Dashboard>}
 */
export async function sharedGetDashboard(projectId, run = 'latest') {
  const q = run ? `?run=${encodeURIComponent(run)}` : '';
  const data = await request(`/shared/projects/${encodeURIComponent(projectId)}/dashboard${q}`);
  return createDashboard(data);
}

/**
 * Get accumulated scores for a shared project.
 * @param {string} projectId
 * @param {string} [asOfRun=null]
 * @returns {Promise<Object>}
 */
export async function sharedGetAccumulated(projectId, asOfRun = null) {
  const q = asOfRun ? `?asOf=${encodeURIComponent(asOfRun)}` : '';
  const data = await request(`/shared/projects/${encodeURIComponent(projectId)}/accumulated${q}`);
  if (data && Array.isArray(data.dimensions)) {
    data.dimensions = data.dimensions.map(createDimension);
  }
  return data;
}

/**
 * Get unified scores for a shared project.
 * @param {string} projectId
 * @param {string} [asOfRun=null]
 * @returns {Promise<{accumulated: Object, trend: Array, availableRuns: Array}>}
 */
export async function sharedGetProjectScores(projectId, asOfRun = null) {
  const q = asOfRun ? `?asOf=${encodeURIComponent(asOfRun)}` : '';
  const data = await request(`/shared/projects/${encodeURIComponent(projectId)}/scores${q}`);
  if (data?.accumulated && Array.isArray(data.accumulated.dimensions)) {
    data.accumulated.dimensions = data.accumulated.dimensions.map(createDimension);
  }
  return data;
}

/**
 * Get slim scores for a specific run.
 * @param {string} projectId
 * @param {string} runId
 * @returns {Promise<{dimensions: Array, summary: Object}>}
 */
export function sharedGetRunScores(projectId, runId) {
  return request(
    `/shared/projects/${encodeURIComponent(projectId)}/scores/${encodeURIComponent(runId)}`
  );
}

// ── Dimension Eval & Violations ─────────────────────────────────────────────

/**
 * Get dimension evaluation details for a shared project.
 * @param {string} projectId
 * @param {string} runId
 * @param {string} dimension
 * @returns {Promise<import('../models/dimension.js').DimensionEval>}
 */
export async function sharedGetDimensionEval(projectId, runId, dimension) {
  const data = await request(
    `/shared/projects/${encodeURIComponent(projectId)}/dimensions/${encodeURIComponent(dimension)}/eval?run=${encodeURIComponent(runId)}`
  );
  return createDimensionEval(data);
}

/**
 * Get violations for a shared project run.
 * @param {string} projectId
 * @param {string} runId
 * @returns {Promise<Object>}
 */
export function sharedGetViolations(projectId, runId) {
  return request(
    `/shared/projects/${encodeURIComponent(projectId)}/violations?run=${encodeURIComponent(runId)}`
  );
}

// ── Publish & Pull ──────────────────────────────────────────────────────────

/**
 * Publish a local project to the shared repository.
 * @param {string} projectId
 * @returns {Promise<{started: boolean}>}
 */
export function publishProject(projectId) {
  return request(`/projects/${encodeURIComponent(projectId)}/publish`, {
    method: 'POST',
  });
}

/**
 * Pull a shared project into the local evaluations.
 * @param {string} projectId
 * @param {string} [action] - 'copy' or 'replace' (resolves collision)
 * @returns {Promise<{imported: boolean, projectId: string}>}
 */
export function pullSharedProject(projectId, action) {
  const body = action ? { action } : {};
  return request(`/shared/projects/${encodeURIComponent(projectId)}/pull`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}
