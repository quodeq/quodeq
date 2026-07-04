/**
 * Findings API — dismissed findings management.
 */

import { request } from './request.js';

// The dismissed list is per-project user data: a single response with all
// entries is fine for any realistic project (a few thousand at most). Ask
// for the server-side hard cap to avoid the API's default page size.
const DISMISSED_REQUEST_LIMIT = 5000;

/**
 * List dismissed findings for a project.
 * @param {string} projectId - Project identifier
 * @returns {Promise<Array>} Dismissed findings array
 */
export async function listDismissedFindings(projectId) {
  return request(
    `/findings/dismissed?project=${encodeURIComponent(projectId)}`
    + `&limit=${DISMISSED_REQUEST_LIMIT}`,
  );
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

/**
 * Permanently delete a finding (suppress by dimension+principle+file forever).
 * @param {string} projectId - Project identifier
 * @param {object} finding - { dimension, principle, file }
 * @returns {Promise<{ok: boolean, swept: number}>} Server response
 */
export async function deleteFinding(projectId, finding) {
  return request('/findings/delete', {
    method: 'POST',
    body: JSON.stringify({ project: projectId, ...finding }),
  });
}

/**
 * Permanently delete all currently-dismissed findings for a project.
 * Each unique (dimension, principle, file) becomes a permanent suppression
 * and the dismissed list is cleared.
 * @param {string} projectId - Project identifier
 * @returns {Promise<{ok: boolean, deleted: number}>} Server response
 */
export async function deleteAllFindings(projectId) {
  return request('/findings/delete-all', {
    method: 'POST',
    body: JSON.stringify({ project: projectId }),
  });
}

/**
 * List verified-badge entries for a project.
 * @param {string} projectId - Project identifier
 * @returns {Promise<Array>} Entries: { req, file, line, note, verifiedAt }
 */
export async function listVerifiedFindings(projectId) {
  return request(`/findings/verified?project=${encodeURIComponent(projectId)}`);
}

/**
 * Clear a verified badge.
 * @param {string} projectId - Project identifier
 * @param {object} finding - Finding key: { req, file, line }
 * @returns {Promise<object>} Server response
 */
export async function unverifyFinding(projectId, finding) {
  return request('/findings/unverify', {
    method: 'POST',
    body: JSON.stringify({
      project: projectId, req: finding.req, file: finding.file, line: finding.line,
    }),
  });
}
