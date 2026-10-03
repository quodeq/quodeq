/**
 * Shared HTTP request helper for the API layer.
 */

export const BASE = import.meta.env.VITE_API_BASE || '/api';
const API_TIMEOUT_MS = 30000;

/**
 * Issues a JSON (or, for a FormData body, multipart) request against the API
 * base and resolves to the parsed body.
 *
 * On a non-2xx response it throws an Error carrying `status` (the HTTP code),
 * `code` (the envelope's stable error code, which strings/apiErrors.js turns
 * into translated copy) and `body` (the raw parsed envelope, so a caller that
 * needs a route-specific field like `existingProjectId` can read it without
 * request() having to know every route's shape). Aborts after
 * `options.timeout` ms, defaulting to 30s; pass `timeout: null` to disable
 * the abort entirely (e.g. a large upload with no time cap).
 *
 * @param {string} path - Path below the API base, e.g. `/projects`.
 * @param {RequestInit & {timeout?: number|null}} [options]
 * @returns {Promise<object>}
 */
export async function request(path, options = {}) {
  // Per-call timeout override: slow mutations (git push + gh can each take up
  // to 120s) pass a larger `timeout` so the client does not falsely report a
  // failure while the backend is still succeeding. `timeout: null` disables
  // it outright. Strip it from the fetch options so it is not forwarded as an
  // unknown init field.
  const { timeout, ...fetchOptions } = options;
  const timeoutMs = timeout === null ? null : (timeout ?? API_TIMEOUT_MS);
  const controller = new AbortController();
  const timeoutId = timeoutMs === null ? null : setTimeout(() => controller.abort(), timeoutMs);
  const signal = fetchOptions.signal
    ? AbortSignal.any([fetchOptions.signal, controller.signal])
    : controller.signal;
  // FormData must not carry the JSON content-type: the browser derives its
  // own multipart boundary from the body and setting Content-Type ourselves
  // breaks that.
  const isFormData = typeof FormData !== 'undefined' && fetchOptions.body instanceof FormData;
  try {
    const res = await fetch(`${BASE}${path}`, {
      headers: isFormData
        ? { ...(fetchOptions.headers || {}) }
        : { 'Content-Type': 'application/json', ...(fetchOptions.headers || {}) },
      ...fetchOptions,
      signal,
    });

    const payload = await res.json().catch(() => ({}));

    if (!res.ok) {
      const err = new Error(payload.error || `Request failed: ${res.status}`);
      // Callers branch on this (e.g. the cancel flow treats 409 as "job no
      // longer cancellable" but keeps the job on transient failures).
      err.status = res.status;
      // The envelope's stable code, which used to be dropped here. err.message
      // is the backend's English and is developer detail; `code` is the only
      // part of the envelope that can be turned into translated copy, so it
      // has to survive the boundary. See strings/apiErrors.js.
      err.code = payload.code ?? null;
      // The full envelope, additive: a route with its own extra fields (e.g.
      // registerProject's existingProjectId) reads them off here instead of
      // every caller re-decoding the response itself.
      err.body = payload;
      throw err;
    }

    return payload;
  } finally {
    if (timeoutId !== null) clearTimeout(timeoutId);
  }
}
