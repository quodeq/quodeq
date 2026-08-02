/**
 * Shared HTTP request helper for the API layer.
 */

export const BASE = import.meta.env.VITE_API_BASE || '/api';
const API_TIMEOUT_MS = 30000;

export async function request(path, options = {}) {
  // Per-call timeout override: slow mutations (git push + gh can each take up
  // to 120s) pass a larger `timeout` so the client does not falsely report a
  // failure while the backend is still succeeding. Strip it from the fetch
  // options so it is not forwarded as an unknown init field.
  const { timeout, ...fetchOptions } = options;
  const timeoutMs = timeout ?? API_TIMEOUT_MS;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  const signal = fetchOptions.signal
    ? AbortSignal.any([fetchOptions.signal, controller.signal])
    : controller.signal;
  try {
    const res = await fetch(`${BASE}${path}`, {
      headers: {
        'Content-Type': 'application/json',
        ...(fetchOptions.headers || {}),
      },
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
      throw err;
    }

    return payload;
  } finally {
    clearTimeout(timeoutId);
  }
}
