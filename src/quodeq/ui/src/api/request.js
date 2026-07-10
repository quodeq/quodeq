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
      throw new Error(payload.error || `Request failed: ${res.status}`);
    }

    return payload;
  } finally {
    clearTimeout(timeoutId);
  }
}
