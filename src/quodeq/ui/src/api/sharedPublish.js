/**
 * Shared repository publish — push a local project to the shared
 * repository. Pulling is a background job: see startPull in api/syncStatus.js.
 */

import { request } from './request.js';
import { projectPath } from './paths.js';

/**
 * Publish a local project to the shared repository.
 * @param {string} projectId
 * @returns {Promise<{started: boolean}>}
 */
export function publishProject(projectId) {
  return request(`${projectPath(projectId)}/publish`, {
    method: 'POST',
  });
}

/**
 * Opt the connected shared repository in to (or out of) receiving code
 * snippets with published findings. Off by default.
 * @param {boolean} withSnippets
 * @returns {Promise<{withSnippets: boolean}>}
 */
export function setSharedSnippets(withSnippets) {
  return request('/shared/snippets', { method: 'PUT', body: JSON.stringify({ withSnippets }) });
}
