/**
 * Shared repository project data — read-only mirrors of the project read
 * endpoints (list/info, dashboard/scores, dimension eval/violations,
 * dismissed/verified findings) against the shared repository clone.
 */

import { request } from './request.js';
import { createProject } from '../models/project.js';
import { createDashboard } from '../models/dashboard.js';
import { createDimension, createDimensionEval, createSlimDimension } from '../models/dimension.js';
import { epochSecondsToMs } from './sharedStatus.js';

// ── Project List & Info ─────────────────────────────────────────────────────

/**
 * List projects from the shared repository.
 * Unlike listProjects's envelope (projects + warmup), this envelope carries sync metadata
 * because the shared tab needs lastSynced and stale status.
 * @param {{refresh?: boolean}} [options={}]
 * @returns {Promise<{projects: import('../models/project.js').Project[], lastSynced: number|null, stale: boolean}>}
 *   Both the envelope's lastSynced and each project's publishedAt are
 *   epoch-milliseconds (converted from the backend's epoch seconds; see
 *   epochSecondsToMs).
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
        proj.publishedAt = epochSecondsToMs(list[idx].publishedAt);
        proj.source = list[idx].source ?? 'shared';
      }
    });
  }

  return {
    projects,
    lastSynced: epochSecondsToMs(data?.lastSynced),
    stale: data?.stale ?? false,
  };
}

/**
 * Get detailed info for a shared project.
 * @param {string} projectId
 * @returns {Promise<import('../models/project.js').Project>}
 *   Like sharedListProjects, publishedBy/publishedAt are passed through
 *   after createProject() (which only knows the base Project shape and
 *   would otherwise silently drop them), with publishedAt converted from
 *   the backend's epoch seconds to epoch-milliseconds.
 */
export async function sharedGetProjectInfo(projectId) {
  const data = await request(`/shared/projects/${encodeURIComponent(projectId)}/info`);
  const project = createProject(data);
  project.publishedBy = data?.publishedBy ?? null;
  project.publishedAt = epochSecondsToMs(data?.publishedAt);
  project.source = data?.source ?? 'shared';
  return project;
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
 * Slim compare-summary for a shared project — the /compare-summary payload
 * served from the shared clone's own evaluations root, shape-identical to
 * the local endpoint so the Compare tab can mix sources row by row.
 * @param {string} projectId
 * @returns {Promise<{project: string, summary: Object, dimensions: Array, trend: Array, runsCount: number, lastRun: Object|null}>}
 */
export async function sharedGetCompareSummary(projectId) {
  const data = await request(`/shared/projects/${encodeURIComponent(projectId)}/compare-summary`);
  if (Array.isArray(data?.dimensions)) data.dimensions = data.dimensions.map(createSlimDimension);
  return data;
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
export async function sharedGetRunScores(projectId, runId) {
  const data = await request(
    `/shared/projects/${encodeURIComponent(projectId)}/scores/${encodeURIComponent(runId)}`
  );
  if (Array.isArray(data?.dimensions)) data.dimensions = data.dimensions.map(createSlimDimension);
  return data;
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
