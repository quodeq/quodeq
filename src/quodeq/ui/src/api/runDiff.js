/**
 * Run diff API: one run classified against another (default: the previous
 * finished run per dimension), with per-requirement counts and the scoped
 * since-baseline lists.
 */
import { request } from './request.js';
import { projectPath } from './paths.js';

/** @returns {Promise<Object>} the raw diff payload (`dimensions[dim].types.perReq`, `dimensions[dim].sinceBaseline.new`, ...) */
export async function getRunDiff(projectId, runId, against = null) {
  const query = against ? `?against=${encodeURIComponent(against)}` : '';
  return request(`${projectPath(projectId)}/runs/${encodeURIComponent(runId)}/diff${query}`);
}
