/**
 * Grade explain API: the scorer's stage values per principle of one
 * dimension in one run, with the stored parameters (GET) or a draft (POST).
 */
import { request } from './request.js';
import { projectPath } from './paths.js';

/** @returns {Promise<{runId: string, dimension: string, params: Object, principles: Array}>} */
export async function getGradeExplain(projectId, runId, dimension) {
  return request(explainPath(projectId, runId, dimension));
}

/**
 * The same payload, recomputed with draft formula parameters.
 * @returns {Promise<{runId: string, dimension: string, params: Object, principles: Array}>}
 */
export async function previewGradeExplain(projectId, runId, dimension, params) {
  return request(explainPath(projectId, runId, dimension), {
    method: 'POST',
    body: JSON.stringify({ params }),
  });
}

function explainPath(projectId, runId, dimension) {
  return `${projectPath(projectId)}/runs/${encodeURIComponent(runId)}/dimensions/${encodeURIComponent(dimension)}/explain`;
}
