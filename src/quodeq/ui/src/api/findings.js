/**
 * Findings API — dismissed findings management.
 */

import { request } from './request.js';

/**
 * List dismissed findings for a project.
 * @param {string} projectId - Project identifier
 * @returns {Promise<Array>} Dismissed findings array
 */
export async function listDismissedFindings(projectId) {
  return request(`/findings/dismissed?project=${encodeURIComponent(projectId)}`);
}

/**
 * Dismiss a finding (exclude from scoring).
 * @param {string} projectId - Project identifier
 * @param {object} finding - Finding data: { req, file, line, dimension, severity, reason }
 * @returns {Promise<object>} Server response
 */
export async function dismissFinding(projectId, finding) {
  return request('/findings/dismiss', {
    method: 'POST',
    body: JSON.stringify({ project: projectId, ...finding }),
  });
}

/**
 * Restore a dismissed finding (include in scoring again).
 * @param {string} projectId - Project identifier
 * @param {object} finding - Finding key: { req, file, line }
 * @returns {Promise<object>} Server response
 */
export async function restoreFinding(projectId, finding) {
  return request('/findings/restore', {
    method: 'POST',
    body: JSON.stringify({ project: projectId, ...finding }),
  });
}

/**
 * Restore all dismissed findings for a project.
 * @param {string} projectId - Project identifier
 * @returns {Promise<{ok: boolean, restored: number}>} Server response
 */
export async function restoreAllFindings(projectId) {
  return request('/findings/restore-all', {
    method: 'POST',
    body: JSON.stringify({ project: projectId }),
  });
}

/**
 * Rescore a project run with dismissed findings filtered out.
 * @param {string} projectId - Project identifier
 * @param {string} [run='latest'] - Run ID (optional, defaults to latest)
 * @returns {Promise<{dimensions: Array, summary: object}>} Rescored data
 */
export async function getRescore(projectId, run = 'latest') {
  const params = new URLSearchParams({ project: projectId });
  if (run && run !== 'latest') params.set('run', run);
  return request(`/rescore?${params}`);
}
