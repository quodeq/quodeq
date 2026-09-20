/**
 * Scores / dashboard API — accumulated and per-run scores, dashboard
 * payloads, and dimension eval detail for a project.
 */

import { createDashboard } from '../models/dashboard.js';
import { createDimensionEval } from '../models/dimension.js';
import { request } from './request.js';
import { asOfQuery, parseAccumulated, parseSlimDimensions, parseUnifiedScores, runQuery } from './scoresShape.js';

// ── Unified Scores ─────────────────────────────────────────────────────

/** @returns {Promise<{accumulated: Object, trend: Array, availableRuns: Array}>} */
export async function getProjectScores(projectId, asOfRun = null) {
  const data = await request(`/projects/${encodeURIComponent(projectId)}/scores${asOfQuery(asOfRun)}`);
  return parseUnifiedScores(data);
}

/** @returns {Promise<{dimensions: Array, summary: Object}>} */
export async function getRunScores(projectId, runId) {
  const data = await request(`/projects/${encodeURIComponent(projectId)}/scores/${encodeURIComponent(runId)}`);
  return parseSlimDimensions(data);
}

/**
 * Slim scores payload for the Compare tab: accumulated summary + dimensions
 * (findings stripped server-side) + trend. One call per project.
 *
 * @returns {Promise<{project: string, summary: Object, dimensions: Array, trend: Array, runsCount: number, lastRun: Object|null}>}
 */
export async function getCompareSummary(projectId) {
  const data = await request(`/projects/${encodeURIComponent(projectId)}/compare-summary`);
  return parseSlimDimensions(data);
}

// ── Dashboard ───────────────────────────────────────────────────────────

/** @returns {Promise<import('../models/dashboard.js').Dashboard>} */
export async function getDashboard(projectId, run = 'latest') {
  const data = await request(`/projects/${encodeURIComponent(projectId)}/dashboard${runQuery(run)}`);
  return createDashboard(data);
}

/** @returns {Promise<Object>} */
export async function getAccumulated(projectId, asOfRun = null) {
  const data = await request(`/projects/${encodeURIComponent(projectId)}/accumulated${asOfQuery(asOfRun)}`);
  return parseAccumulated(data);
}

// ── Dimension Eval ──────────────────────────────────────────────────────

/** @returns {Promise<import('../models/dimension.js').DimensionEval>} */
export async function getDimensionEval(projectId, runId, dimension) {
  const data = await request(
    `/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/dimensions/${encodeURIComponent(dimension)}/eval`
  );
  return createDimensionEval(data);
}
