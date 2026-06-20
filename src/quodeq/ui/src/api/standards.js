/**
 * Standards API — standard CRUD and library operations.
 */

import { request, BASE } from './request.js';

/** @returns {Promise<Object[]>} */
export async function listStandards() {
  return request('/standards');
}

/**
 * @param {string} standardId
 * @returns {Promise<Object>}
 */
export async function getStandard(standardId) {
  return request(`/standards/${encodeURIComponent(standardId)}`);
}

/**
 * @param {Object} data - Standard definition
 * @returns {Promise<Object>}
 */
export async function createStandard(data) {
  return request('/standards', { method: 'POST', body: JSON.stringify(data) });
}

/**
 * @param {string} standardId
 * @param {Object} data - Updated standard definition
 * @returns {Promise<Object>}
 */
export async function updateStandard(standardId, data) {
  return request(`/standards/${encodeURIComponent(standardId)}`, { method: 'PUT', body: JSON.stringify(data) });
}

/**
 * @param {string} standardId
 * @returns {Promise<Object>}
 */
export async function deleteStandard(standardId) {
  return request(`/standards/${encodeURIComponent(standardId)}`, { method: 'DELETE' });
}

/**
 * @param {string} standardId
 * @param {string} newId
 * @returns {Promise<Object>}
 */
export async function duplicateStandard(standardId, newId) {
  return request(`/standards/${encodeURIComponent(standardId)}/duplicate`, { method: 'POST', body: JSON.stringify({ newId }) });
}

/** @returns {Promise<Object[]>} */
export async function listLibrary() {
  return request('/standards/library');
}

/** @returns {Promise<Object[]>} */
export async function listCwes() {
  return request('/standards/refs/cwe');
}

/**
 * @param {string} file - Library file identifier
 * @returns {Promise<Object>}
 */
export async function importFromLibrary(file) {
  return request('/standards/library/import', { method: 'POST', body: JSON.stringify({ file }) });
}

/**
 * @param {Object} data - Standard data to import
 * @param {boolean} [force=false] - Overwrite existing standard if true
 * @returns {Promise<Object>} Result with optional `_conflict` flag
 */
export async function importStandard(data, force = false) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 30000);
  let res;
  try {
    res = await fetch(`${BASE}/standards/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ data, force }),
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeoutId);
  }
  const body = await res.json().catch(() => ({}));
  if (res.status === 409) return { ...body, _conflict: true };
  if (!res.ok) throw new Error(body.error || `Import failed: ${res.status}`);
  return body;
}

/**
 * Fetch a standard and return a portable (non-managed) representation.
 * @param {string} standardId
 * @returns {Promise<{ id: string, data: Object, fileName: string }>}
 */
export async function exportStandard(standardId) {
  const detail = await getStandard(standardId);
  const { managed, type, origin, originHash, principleCount, requirementCount, ...portable } = detail;
  return { id: standardId, data: portable, fileName: `${standardId}.quodeq` };
}
