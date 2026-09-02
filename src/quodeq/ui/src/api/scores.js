/**
 * Scores / dashboard API — accumulated and per-run scores, dashboard
 * payloads, and dimension eval detail for a project.
 */

import { createDashboard } from '../models/dashboard.js';
import { createDimension, createDimensionEval, createSlimDimension } from '../models/dimension.js';
import { request } from './request.js';

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

// ── Dimension Eval ──────────────────────────────────────────────────────

/** @returns {Promise<import('../models/dimension.js').DimensionEval>} */
export async function getDimensionEval(projectId, runId, dimension) {
  const data = await request(
    `/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/dimensions/${encodeURIComponent(dimension)}/eval`
  );
  return createDimensionEval(data);
}
