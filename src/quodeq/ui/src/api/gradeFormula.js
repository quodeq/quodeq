/**
 * Grade formula API — current/custom grade formula, preview against a run.
 */

import { request } from './request.js';

/** @returns {Promise<{current: Object, defaults: Object, isCustom: boolean, rescore: {state: string, generation: number, appliedGeneration: number, done: number, total: number, failed: number}}>} */
export function getGradeFormula() {
  return request('/grade-formula');
}

// PUT and DELETE answer 202: the rescore runs in the background; poll getGradeFormula for progress.
/** @returns {Promise<{current: Object, defaults: Object, isCustom: boolean, rescore: {state: string, generation: number, appliedGeneration: number, done: number, total: number, failed: number}}>} */
export function saveGradeFormula(params) {
  return request('/grade-formula', { method: 'PUT', body: JSON.stringify(params) });
}

/** @returns {Promise<{current: Object, defaults: Object, isCustom: boolean, rescore: {state: string, generation: number, appliedGeneration: number, done: number, total: number, failed: number}}>} */
export function resetGradeFormula() {
  return request('/grade-formula?confirm=true', { method: 'DELETE' });
}

/** @returns {Promise<{project: string, runId: string, before: Object, after: Object}>} */
export function previewGradeFormula(projectId, params) {
  return request('/grade-formula/preview', {
    method: 'POST',
    body: JSON.stringify({ project: projectId, params }),
  });
}
