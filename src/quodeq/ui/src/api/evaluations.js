/**
 * Evaluations / jobs API — start, poll, cancel, and delete evaluation runs.
 */

import { createJob } from '../models/job.js';
import { request } from './request.js';

/**
 * @param {{ limit?: number, states?: string[] }} [options]
 * @returns {Promise<import('../models/job.js').Job[]>}
 */
export async function listEvaluations({ limit, states } = {}) {
  const params = new URLSearchParams();
  if (limit) params.set('limit', String(limit));
  if (states && states.length) params.set('state', states.join(','));
  const qs = params.toString();
  const data = await request(`/evaluations${qs ? `?${qs}` : ''}`);
  return (data || []).map(createJob);
}

/** @returns {Promise<import('../models/job.js').Job>} */
export async function startEvaluation(input) {
  const data = await request('/evaluations', {
    method: 'POST',
    body: JSON.stringify(input),
  });
  return createJob(data);
}

/** @returns {Promise<import('../models/job.js').Job>} */
export async function getEvaluation(jobId) {
  const data = await request(`/evaluations/${encodeURIComponent(jobId)}`);
  return createJob(data);
}

/**
 * Live progress for a scan. Pure on-disk read — works for internal and
 * external (CLI-started) runs uniformly.
 * @param {string} jobId
 * @returns {Promise<Object>}
 */
export function getEvaluationProgress(jobId) {
  return request(`/evaluations/${encodeURIComponent(jobId)}/progress`);
}

/**
 * Cancel a running evaluation. Declares intent=cancel so the server can
 * never route this to the permanent-purge branch, even if the run finished
 * while the confirm dialog was open (it 409s instead and the run is kept).
 * @param {string} jobId
 * @param {{discard?: boolean}} [opts]
 * @returns {Promise<Object>}
 */
export function cancelEvaluation(jobId, opts = {}) {
  const qs = opts.discard ? '?intent=cancel&discard=true' : '?intent=cancel';
  // The server-side cancel path can block for the full SIGTERM grace window
  // (~30s) plus the terminal-status wait before responding; the default 30s
  // request timeout aborted client-side right before the backend finished.
  return request(`/evaluations/${encodeURIComponent(jobId)}${qs}`, { method: 'DELETE', timeout: 45000 });
}

/**
 * Permanently delete a non-running evaluation from history (removes scan
 * dir + index row). Declares intent=delete so a run that is unexpectedly
 * still running is refused (409) instead of being silently cancelled.
 * @param {string} jobId
 * @returns {Promise<Object>}
 */
export function deleteEvaluation(jobId) {
  return request(`/evaluations/${encodeURIComponent(jobId)}?intent=delete`, { method: 'DELETE' });
}
