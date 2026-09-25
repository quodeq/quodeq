/**
 * Scores / dashboard API — accumulated and per-run scores, dashboard
 * payloads, and dimension eval detail for a project.
 */

import { createDashboard } from '../models/dashboard.js';
import { createDimensionEval } from '../models/dimension.js';
import { request } from './request.js';
import { attachComplianceDetailRefs } from './complianceDetail.js';
import { createViolations } from '../models/violation.js';
import { asOfQuery, parseAccumulated, parseSlimDimensions, parseUnifiedScores, runQuery } from './scoresShape.js';
import { LATEST_RUN_ID } from '../constants.js';
import { projectPath } from './paths.js';

// ── Unified Scores ─────────────────────────────────────────────────────

// Numbers each /scores response, so compliance detail fetched for one
// response is never merged into another (see attachComplianceDetailRefs).
let scoresGeneration = 0;

/** @returns {Promise<{accumulated: Object, trend: Array, availableRuns: Array}>} */
export async function getProjectScores(projectId, asOfRun = null) {
  const data = await request(`${projectPath(projectId)}/scores${asOfQuery(asOfRun)}`);
  scoresGeneration += 1;
  return attachComplianceDetailRefs(parseUnifiedScores(data), projectId, asOfRun, scoresGeneration);
}

/**
 * Full compliance items /scores deferred, for one accumulated dimension.
 * @param {string} projectId
 * @param {{dimension: string, asOf?: string|null, principle?: string, pathPrefix?: string}} scope
 * @returns {Promise<import('../models/violation.js').Violation[]>}
 */
export async function getComplianceDetail(projectId, { dimension, asOf, principle, pathPrefix }) {
  const params = new URLSearchParams({ dimension });
  if (asOf) params.set('asOf', asOf);
  if (principle) params.set('principle', principle);
  if (pathPrefix) params.set('pathPrefix', pathPrefix);
  const data = await request(`${projectPath(projectId)}/compliance-detail?${params}`);
  return createViolations(data?.items);
}

/** @returns {Promise<{dimensions: Array, summary: Object}>} */
export async function getRunScores(projectId, runId) {
  const data = await request(`${projectPath(projectId)}/scores/${encodeURIComponent(runId)}`);
  return parseSlimDimensions(data);
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

// ── Dashboard ───────────────────────────────────────────────────────────

/** @returns {Promise<import('../models/dashboard.js').Dashboard>} */
export async function getDashboard(projectId, run = LATEST_RUN_ID) {
  const data = await request(`${projectPath(projectId)}/dashboard${runQuery(run)}`);
  return createDashboard(data);
}

/** @returns {Promise<Object>} */
export async function getAccumulated(projectId, asOfRun = null) {
  const data = await request(`${projectPath(projectId)}/accumulated${asOfQuery(asOfRun)}`);
  return parseAccumulated(data);
}

// ── Dimension Eval ──────────────────────────────────────────────────────

/** @returns {Promise<import('../models/dimension.js').DimensionEval>} */
export async function getDimensionEval(projectId, runId, dimension) {
  const data = await request(
    `${projectPath(projectId)}/runs/${encodeURIComponent(runId)}/dimensions/${encodeURIComponent(dimension)}/eval`
  );
  return createDimensionEval(data);
}
