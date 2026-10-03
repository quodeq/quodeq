/**
 * Scores / dashboard API — accumulated and per-run scores, dashboard
 * payloads, and dimension eval detail for a project.
 */

import { createDashboard } from '../models/dashboard.js';
import { createDimensionEval } from '../models/dimension.js';
import { request } from './request.js';
import { attachEvalFindingDetailRefs, attachFindingDetailRefs, attachRunFindingDetailRefs } from './complianceDetail.js';
import { FINDING_TYPE } from '../vocab/findingType.js';
import { createViolations } from '../models/violation.js';
import { asOfQuery, findingDetailQuery, parseAccumulated, parseFleetCompare, parseSlimDimensions, parseUnifiedScores } from './scoresShape.js';
import { LATEST_RUN_ID } from '../constants.js';
import { DASHBOARD_VIEW } from '../vocab/dashboardView.js';
import { fleetQuery, projectPath } from './paths.js';

// ── Unified Scores ─────────────────────────────────────────────────────

// Numbers each /scores response, so compliance detail fetched for one
// response is never merged into another (see attachComplianceDetailRefs).
let scoresGeneration = 0;

/** @returns {Promise<{accumulated: Object, trend: Array, availableRuns: Array}>} */
export async function getProjectScores(projectId, asOfRun = null) {
  const data = await request(`${projectPath(projectId)}/scores${asOfQuery(asOfRun)}`);
  scoresGeneration += 1;
  return attachFindingDetailRefs(parseUnifiedScores(data), projectId, asOfRun, scoresGeneration);
}

/**
 * Full items of one kind that /scores (accumulated, `asOf`) or
 * /scores/<run> (`run`) deferred, for one dimension.
 * @param {string} projectId
 * @param {{kind: string, dimension: string, run?: string|null, asOf?: string|null, principle?: string, pathPrefix?: string}} scope
 *   `kind` is FINDING_TYPE.VIOLATION or FINDING_TYPE.COMPLIANCE.
 * @returns {Promise<import('../models/violation.js').Violation[]>}
 */
export async function getFindingDetail(projectId, scope) {
  const data = await request(`${projectPath(projectId)}/compliance-detail?${findingDetailQuery(scope)}`);
  return createViolations(data?.items);
}

/**
 * `getFindingDetail` for compliance items (the pre-kind entry point).
 * @param {string} projectId
 * @param {{dimension: string, asOf?: string|null, principle?: string, pathPrefix?: string}} scope
 * @returns {Promise<import('../models/violation.js').Violation[]>}
 */
export function getComplianceDetail(projectId, scope) {
  return getFindingDetail(projectId, { ...scope, kind: FINDING_TYPE.COMPLIANCE });
}

/**
 * One run's rescored dimensions with finding detail deferred (see
 * attachRunFindingDetailRefs).
 * @returns {Promise<{dimensions: Array, summary: Object}>}
 */
export async function getRunScores(projectId, runId) {
  const data = await request(`${projectPath(projectId)}/scores/${encodeURIComponent(runId)}`);
  return attachRunFindingDetailRefs(parseSlimDimensions(data), projectId, runId);
}

/**
 * Slim scores payload for the Compare tab: accumulated summary + dimensions
 * (findings stripped server-side) + trend. One call per project.
 *
 * @returns {Promise<{project: string, summary: Object, dimensions: Array, trend: Array, runsCount: number, lastRun: Object|null}>}
 */
export async function getCompareSummary(projectId) {
  const data = await request(`${projectPath(projectId)}/compare-summary`);
  return parseSlimDimensions(data);
}

/**
 * The compare summaries of a whole fleet in one request. A project the
 * server could not serve is named in `errors` instead of failing the call.
 * @param {string[]} projectIds
 * @returns {Promise<{summaries: Array<Object>, errors: Object<string, string>}>}
 */
export async function getFleetCompare(projectIds) {
  const data = await request(`/fleet/compare${fleetQuery(projectIds)}`);
  return parseFleetCompare(data);
}

// ── Dashboard ───────────────────────────────────────────────────────────

/**
 * @param {string} projectId
 * @param {string|null} run  LATEST_RUN_ID or a run id; falsy means the server default
 * @returns {Promise<import('../models/dashboard.js').Dashboard>} the
 *   overview shape: scores and counts, no finding lists (see getRunScores)
 */
export async function getDashboard(projectId, run = LATEST_RUN_ID) {
  const query = new URLSearchParams();
  if (run) query.set('run', run);
  query.set('view', DASHBOARD_VIEW.OVERVIEW);
  const data = await request(`${projectPath(projectId)}/dashboard?${query}`);
  return createDashboard(data);
}

/** @returns {Promise<Object>} */
export async function getAccumulated(projectId, asOfRun = null) {
  const data = await request(`${projectPath(projectId)}/accumulated${asOfQuery(asOfRun)}`);
  return parseAccumulated(data);
}

// ── Dimension Eval ──────────────────────────────────────────────────────

/**
 * One run's eval for a dimension. A finished run's items come with their
 * detail deferred to /compliance-detail?run= (see attachEvalFindingDetailRefs).
 * @returns {Promise<import('../models/dimension.js').DimensionEval>}
 */
export async function getDimensionEval(projectId, runId, dimension) {
  const data = await request(
    `${projectPath(projectId)}/runs/${encodeURIComponent(runId)}/dimensions/${encodeURIComponent(dimension)}/eval`
  );
  return attachEvalFindingDetailRefs(createDimensionEval(data), projectId, runId);
}
