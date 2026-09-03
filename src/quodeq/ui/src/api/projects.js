/**
 * Projects API — registration, lookup, scan, delete/relocate, export/import,
 * and the directory browser used by the onboarding wizard's Repo & Scan step.
 */

import { createProject } from '../models/project.js';
import { request, BASE } from './request.js';

// ── Health ──────────────────────────────────────────────────────────────

export function getHealth() {
  return request('/health');
}

// ── Projects ────────────────────────────────────────────────────────────

// First startup after an upgrade can invalidate the backend's score caches,
// making the first /projects response take minutes, not seconds. The default
// 30s abort turned that into an abandon-and-re-request loop that multiplied
// the backend's recompute; the server single-flights the build now, and this
// wider window lets one request wait it out instead of churning.
const PROJECTS_LIST_TIMEOUT_MS = 120000;

/** @returns {Promise<{ projects: import('../models/project.js').Project[], warmup: object | null }>} */
export async function listProjects() {
  const data = await request('/projects', { timeout: PROJECTS_LIST_TIMEOUT_MS });
  const list = data?.projects ?? data ?? [];
  return {
    projects: Array.isArray(list) ? list.map(createProject) : [],
    warmup: (data && !Array.isArray(data) && data.warmup) || null,
  };
}

/** @returns {Promise<import('../models/project.js').Project>} */
export async function getProjectInfo(projectId) {
  const data = await request(`/projects/${encodeURIComponent(projectId)}/info`);
  return createProject(data);
}

/**
 * Scan summary for a registered project (file counts, languages, branches).
 *
 * `signal` lets a caller cap the wait with its own AbortSignal (e.g.
 * `AbortSignal.timeout(...)`); pass a matching `timeout` alongside it when
 * the cap exceeds request()'s 30s default, or the internal timer aborts
 * first. Rejects on any non-2xx response, like every other adapter call.
 *
 * @param {string} projectId
 * @param {{ signal?: AbortSignal, timeout?: number }} [options]
 * @returns {Promise<Object>} raw scan payload
 */
export function getProjectScan(projectId, { signal, timeout } = {}) {
  return request(`/projects/${encodeURIComponent(projectId)}/scan`, { signal, timeout });
}

/**
 * @param {string} projectId
 * @returns {Promise<Object>}
 */
export function deleteProject(projectId) {
  return request(`/projects/${encodeURIComponent(projectId)}?confirm=true`, { method: 'DELETE' });
}

/**
 * @param {string} projectId
 * @returns {string} Download URL for the project export
 */
export function getProjectExportUrl(projectId) {
  return `${BASE}/projects/${encodeURIComponent(projectId)}/export`;
}

/**
 * @param {string} projectId
 * @param {string} newPath
 * @returns {Promise<Object>}
 */
export function relocateProject(projectId, newPath) {
  return request(`/projects/${encodeURIComponent(projectId)}/path`, {
    method: 'PATCH',
    body: JSON.stringify({ path: newPath }),
  });
}

// ── Browse / Plugins ────────────────────────────────────────────────────

/**
 * @param {string} [dirPath='']
 * @param {{ files?: boolean }} [options]
 * @returns {Promise<{ current: string, parent: string|null, directories: Object[], files?: Object[] }>}
 */
export function browseDirectory(dirPath = '', options = {}) {
  const params = new URLSearchParams();
  if (dirPath) params.set('path', dirPath);
  if (options.files) params.set('files', '1');
  const q = params.toString() ? `?${params}` : '';
  return request(`/browse${q}`);
}

/**
 * @param {string} path - Parent directory path
 * @param {string} name - New directory name
 * @returns {Promise<Object>}
 */
export function createDirectory(path, name) {
  return request('/browse/mkdir', {
    method: 'POST',
    body: JSON.stringify({ path, name }),
  });
}

/** @returns {Promise<Object[]>} */
export function listPlugins() {
  return request('/plugins');
}

/** @returns {Promise<Object>} Scan results for the given directory path */
export function scanPath(dirPath) {
  return request('/scan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: dirPath }) });
}

// Standards and findings APIs live in their own modules (see api/index.js).

/**
 * Import a previously-exported project zip.
 *
 * Uses raw fetch so we can (a) send multipart/form-data without the shared
 * request() wrapper forcing application/json, and (b) read err.status,
 * err.kind, err.existingProjectId on a 409 collision so the caller can
 * prompt the user to choose Replace / Import as copy / Cancel.
 *
 * @param {File|Blob} file - the .zip file to import
 * @param {{ action?: 'replace'|'copy' }} [opts]
 * @returns {Promise<{ imported: boolean, projectId: string, sourceProjectId: string, renamed: boolean, projectName?: string }>}
 * @throws {Error & { status: number, code?: string, kind?: string, existingProjectId?: string, projectName?: string }} on non-2xx
 */
export async function importProject(file, opts = {}) {
  const form = new FormData();
  form.append('file', file);
  if (opts.action) form.append('action', opts.action);
  // No timeout: large project zips can take a while to upload.
  const res = await fetch(`${BASE}/projects/import`, { method: 'POST', body: form });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(body.error || `importProject failed (${res.status})`);
    err.status = res.status;
    if (body.code) err.code = body.code;
    if (body.kind) err.kind = body.kind;
    if (body.existingProjectId) err.existingProjectId = body.existingProjectId;
    if (body.projectName) err.projectName = body.projectName;
    throw err;
  }
  return body;
}

// Note: uses raw fetch (not the shared request() wrapper) so the wizard can
// read err.status and err.existingProjectId on a 409 duplicate response —
// request() throws plain Error and discards both. Refactoring request() to
// enrich errors is a separate concern.

/**
 * Register a new project without starting an evaluation.
 * Used by the onboarding wizard's Repo & Scan step.
 *
 * @param {{ repo: string, cloneDest?: string, ephemeral?: boolean, branch?: string, scopePath?: string, discipline?: string }} payload
 * @returns {Promise<{ projectId: string, scanData: object }>}
 * @throws {Error & { status: number, code?: string, existingProjectId?: string }} on non-2xx
 */
export async function registerProject(payload) {
  let res;
  try {
    res = await fetch(`${BASE}/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      // Generous: registration may clone a large repository server-side,
      // but a hung backend must not leave onboarding pending forever.
      signal: AbortSignal.timeout(600000), // 10 min
    });
  } catch (e) {
    if (e?.name === 'TimeoutError' || e?.name === 'AbortError') {
      throw new Error('Project registration timed out. The server may be unresponsive or the clone is taking too long; try again.');
    }
    throw e;
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(body.error || `registerProject failed (${res.status})`);
    err.status = res.status;
    if (body.code) err.code = body.code;
    if (body.existingProjectId) err.existingProjectId = body.existingProjectId;
    throw err;
  }
  return body;
}
