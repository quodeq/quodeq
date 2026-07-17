/**
 * Shared repository API client — read-only mirrors of the project read endpoints,
 * plus config management (connect, disconnect, refresh, status) and publish/pull.
 */

import { request, BASE } from './request.js';
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
 * Unlike listProjects (returns bare array), this returns an envelope with sync metadata
 * because the shared tab needs lastSynced and stale status.
 * @param {{refresh?: boolean}} [options={}]
 * @returns {Promise<{projects: import('../models/project.js').Project[], lastSynced: string|null, stale: boolean}>}
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

  return {
    projects,
    lastSynced: data?.lastSynced ?? null,
    stale: data?.stale ?? false,
  };
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

// ── Findings (read-only mirrors) ────────────────────────────────────────────
// Shared projects are read-only in the app — there are no shared mutation
// routes (dismiss/restore/delete/unverify), only these list mirrors so the
// dismissed/verified sub-tabs can display a shared project's existing state.

// Mirrors the local listDismissedFindings' server-side hard cap (see
// api/findings.js DISMISSED_REQUEST_LIMIT) so a shared project's dismissed
// list isn't silently truncated to the API's default page size.
const SHARED_DISMISSED_REQUEST_LIMIT = 5000;

/**
 * List dismissed findings for a shared project.
 * @param {string} projectId
 * @returns {Promise<Array>} Dismissed findings array (same item shape as listDismissedFindings)
 */
export function sharedListDismissedFindings(projectId) {
  return request(
    `/shared/projects/${encodeURIComponent(projectId)}/findings/dismissed`
    + `?limit=${SHARED_DISMISSED_REQUEST_LIMIT}`
  );
}

/**
 * List verified-badge entries for a shared project.
 * @param {string} projectId
 * @returns {Promise<Array>} Entries: { req, file, line, note, verifiedAt }
 */
export function sharedListVerifiedFindings(projectId) {
  return request(`/shared/projects/${encodeURIComponent(projectId)}/findings/verified`);
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
 *
 * Uses raw fetch (not the shared request() wrapper) so a 409 collision
 * response can be read as err.status/err.kind/err.existingProjectId/
 * err.projectName -- same contract as importProject() in api/index.js,
 * since both funnel through the backend's import_zip_stream. The
 * "pull local copy" footer action on the online Projects tab needs
 * err.status === 409 to show its inline copy-confirm affordance.
 *
 * @param {string} projectId
 * @param {string} [action] - 'copy' or 'replace' (resolves a 409 collision)
 * @returns {Promise<{imported: boolean, projectId: string}>}
 * @throws {Error & { status: number, code?: string, kind?: string, existingProjectId?: string, projectName?: string }} on non-2xx
 */
export async function pullSharedProject(projectId, action) {
  const body = action ? { action } : {};
  const res = await fetch(`${BASE}/shared/projects/${encodeURIComponent(projectId)}/pull`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(payload.error || `pullSharedProject failed (${res.status})`);
    err.status = res.status;
    if (payload.code) err.code = payload.code;
    if (payload.kind) err.kind = payload.kind;
    if (payload.existingProjectId) err.existingProjectId = payload.existingProjectId;
    if (payload.projectName) err.projectName = payload.projectName;
    throw err;
  }
  return payload;
}
