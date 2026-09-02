/**
 * Shared repository publish/pull — push a local project to the shared
 * repository, or pull a shared project into local evaluations.
 */

import { request, BASE } from './request.js';

/**
 * Publish a local project to the shared repository.
 * @param {string} projectId
 * @returns {Promise<{started: boolean}>}
 */
export function publishProject(projectId) {
  return request(`/projects/${encodeURIComponent(projectId)}/publish`, {
    method: 'POST',
  });
}

/**
 * Pull a shared project into the local evaluations.
 *
 * Uses raw fetch (not the shared request() wrapper) so a 409 collision
 * response can be read as err.status/err.kind/err.existingProjectId/
 * err.projectName -- same contract as importProject() in api/index.js,
 * since both funnel through the backend's import_zip_stream. The
 * "pull local copy" footer action on the online Projects tab needs
 * err.status === 409 to show its inline copy-confirm affordance.
 *
 * @param {string} projectId
 * @param {string} [action] - 'copy' or 'replace' (resolves a 409 collision)
 * @returns {Promise<{imported: boolean, projectId: string}>}
 * @throws {Error & { status: number, code?: string, kind?: string, existingProjectId?: string, projectName?: string }} on non-2xx
 */
export async function pullSharedProject(projectId, action) {
  const body = action ? { action } : {};
  let res;
  try {
    res = await fetch(`${BASE}/shared/projects/${encodeURIComponent(projectId)}/pull`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      // Generous: a pull imports a zip stream from the shared repository,
      // but a stalled connection must not leave the pull pending forever.
      signal: AbortSignal.timeout(600000), // 10 min
    });
  } catch (e) {
    if (e?.name === 'TimeoutError' || e?.name === 'AbortError') {
      throw new Error('Pull timed out. Check the shared repository connection and try again.');
    }
    throw e;
  }
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(payload.error || `pullSharedProject failed (${res.status})`);
    err.status = res.status;
    if (payload.code) err.code = payload.code;
    if (payload.kind) err.kind = payload.kind;
    if (payload.existingProjectId) err.existingProjectId = payload.existingProjectId;
    if (payload.projectName) err.projectName = payload.projectName;
    throw err;
  }
  return payload;
}
