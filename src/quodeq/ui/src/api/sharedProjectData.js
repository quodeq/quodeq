/**
 * Shared repository project data — read-only mirrors of the project read
 * endpoints (list/info, dashboard/scores, dimension eval/violations,
 * dismissed/verified findings) against the shared repository clone.
 */

import { request } from './request.js';
import { createProject } from '../models/project.js';
import { createDashboard } from '../models/dashboard.js';
import { createDimensionEval } from '../models/dimension.js';
import { epochSecondsToMs } from './sharedStatus.js';
import { LATEST_RUN_ID } from '../constants.js';
import { asOfQuery, findingDetailQuery, isPendingPayload, parseAccumulated, parseFleetCompare, parseSlimDimensions, parseUnifiedScores, runQuery } from './scoresShape.js';
import { attachEvalFindingDetailRefs, attachRunFindingDetailRefs } from './complianceDetail.js';
import { createViolations } from '../models/violation.js';
import { PROJECT_SOURCE } from '../vocab/projectSource.js';
import { fleetQuery, sharedProjectPath } from './paths.js';

// ── Project List & Info ─────────────────────────────────────────────────────

// The first listing of a freshly cloned repository computes every project
// card inline on the server and can take longer than the default 30s abort.
// The connect and refresh jobs warm it before reporting done, so this wider
// window is the safety net for a listing that still lands cold.
const SHARED_LIST_TIMEOUT_MS = 120000;

/**
 * List projects from the shared repository.
 * Unlike listProjects's envelope, this envelope carries sync metadata
 * because the shared tab needs lastSynced and stale status.
 * @param {{refresh?: boolean}} [options={}]
 * @returns {Promise<{projects: import('../models/project.js').Project[], lastSynced: number|null, stale: boolean}>}
 *   Both the envelope's lastSynced and each project's publishedAt are
 *   epoch-milliseconds (converted from the backend's epoch seconds; see
 *   epochSecondsToMs).
 */
export async function sharedListProjects({ refresh = false } = {}) {
  const refreshParam = refresh ? '1' : '0';
  const data = await request(`/shared/projects?refresh=${refreshParam}`, { timeout: SHARED_LIST_TIMEOUT_MS });
  const list = data?.projects ?? data ?? [];
  const projects = Array.isArray(list) ? list.map(createProject) : [];

  // Pass through shared-specific metadata
  if (Array.isArray(list)) {
    projects.forEach((proj, idx) => {
      if (list[idx]) {
        proj.publishedBy = list[idx].publishedBy ?? null;
        proj.publishedAt = epochSecondsToMs(list[idx].publishedAt);
        proj.source = list[idx].source ?? PROJECT_SOURCE.SHARED;
      }
    });
  }

  return {
    projects,
    lastSynced: epochSecondsToMs(data?.lastSynced),
    stale: data?.stale ?? false,
    // The server keeps a card off the listing until its worker has warmed
    // it and counts the rest here; the page shows a placeholder per card
    // still to come and re-lists while this is active.
    warmup: data?.warmup ?? null,
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
  const data = await request(`${sharedProjectPath(projectId)}/info`);
  const project = createProject(data);
  project.publishedBy = data?.publishedBy ?? null;
  project.publishedAt = epochSecondsToMs(data?.publishedAt);
  project.source = data?.source ?? PROJECT_SOURCE.SHARED;
  return project;
}

/**
 * Get runs for a shared project.
 * @param {string} projectId
 * @returns {Promise<{runs: Array}>}
 */
export function sharedGetRuns(projectId) {
  return request(`${sharedProjectPath(projectId)}/runs`);
}

// ── Dashboard & Scores ──────────────────────────────────────────────────────

/**
 * Get dashboard for a shared project run.
 * @param {string} projectId
 * @param {string} [run='latest']
 * @returns {Promise<import('../models/dashboard.js').Dashboard>}
 */
export async function sharedGetDashboard(projectId, run = LATEST_RUN_ID) {
  const data = await request(`${sharedProjectPath(projectId)}/dashboard${runQuery(run)}`);
  // A pending body (the server's warm-up still owes the project) is handed
  // through untouched so the hooks poll on it; same for the two below.
  return isPendingPayload(data) ? data : createDashboard(data);
}

/**
 * Slim compare-summary for a shared project — the /compare-summary payload
 * served from the shared clone's own evaluations root, shape-identical to
 * the local endpoint so the Compare tab can mix sources row by row.
 * @param {string} projectId
 * @returns {Promise<{project: string, summary: Object, dimensions: Array, trend: Array, runsCount: number, lastRun: Object|null}>}
 */
export async function sharedGetCompareSummary(projectId) {
  const data = await request(`${sharedProjectPath(projectId)}/compare-summary`);
  return parseSlimDimensions(data);
}

/**
 * The compare summaries of a fleet of shared projects in one request.
 * @param {string[]} projectIds
 * @returns {Promise<{summaries: Array<Object>, errors: Object<string, string>}>}
 */
export async function sharedGetFleetCompare(projectIds) {
  const data = await request(`/shared/fleet/compare${fleetQuery(projectIds)}`);
  return parseFleetCompare(data);
}

/**
 * Get accumulated scores for a shared project.
 * @param {string} projectId
 * @param {string} [asOfRun=null]
 * @returns {Promise<Object>}
 */
export async function sharedGetAccumulated(projectId, asOfRun = null) {
  const data = await request(`${sharedProjectPath(projectId)}/accumulated${asOfQuery(asOfRun)}`);
  return isPendingPayload(data) ? data : parseAccumulated(data);
}

/**
 * Get unified scores for a shared project.
 * @param {string} projectId
 * @param {string} [asOfRun=null]
 * @returns {Promise<{accumulated: Object, trend: Array, availableRuns: Array}>}
 */
export async function sharedGetProjectScores(projectId, asOfRun = null) {
  const data = await request(`${sharedProjectPath(projectId)}/scores${asOfQuery(asOfRun)}`);
  return isPendingPayload(data) ? data : parseUnifiedScores(data);
}

/**
 * One run's rescored dimensions with finding detail deferred, from the
 * shared mirror (`sharedGetFindingDetail` refills it).
 * @param {string} projectId
 * @param {string} runId
 * @returns {Promise<{dimensions: Array, summary: Object}>}
 */
export async function sharedGetRunScores(projectId, runId) {
  const data = await request(
    `${sharedProjectPath(projectId)}/scores/${encodeURIComponent(runId)}`
  );
  return attachRunFindingDetailRefs(parseSlimDimensions(data), projectId, runId, PROJECT_SOURCE.SHARED);
}

/**
 * `getFindingDetail` against the shared mirror.
 * @param {string} projectId
 * @param {{kind: string, dimension: string, run?: string|null, asOf?: string|null, principle?: string, pathPrefix?: string}} scope
 * @returns {Promise<import('../models/violation.js').Violation[]>}
 */
export async function sharedGetFindingDetail(projectId, scope) {
  const data = await request(`${sharedProjectPath(projectId)}/compliance-detail?${findingDetailQuery(scope)}`);
  return createViolations(data?.items);
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
    `${sharedProjectPath(projectId)}/dimensions/${encodeURIComponent(dimension)}/eval?run=${encodeURIComponent(runId)}`
  );
  return attachEvalFindingDetailRefs(createDimensionEval(data), projectId, runId, PROJECT_SOURCE.SHARED);
}

/**
 * Get violations for a shared project run.
 * @param {string} projectId
 * @param {string} runId
 * @returns {Promise<Object>}
 */
export function sharedGetViolations(projectId, runId) {
  return request(
    `${sharedProjectPath(projectId)}/violations?run=${encodeURIComponent(runId)}`
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
    `${sharedProjectPath(projectId)}/findings/dismissed`
    + `?limit=${SHARED_DISMISSED_REQUEST_LIMIT}`
  );
}

/**
 * List verified-badge entries for a shared project.
 * @param {string} projectId
 * @returns {Promise<Array>} Entries: { req, file, line, note, verifiedAt }
 */
export function sharedListVerifiedFindings(projectId) {
  return request(`${sharedProjectPath(projectId)}/findings/verified`);
}
