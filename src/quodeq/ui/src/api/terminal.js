import { request, BASE } from './request.js';

/**
 * The WebSocket URL for the embedded terminal, derived from the page origin
 * so it follows the dev proxy and https. Pass `sessionId` to attach to an
 * existing session instead of the default one.
 *
 * @returns {string}
 */
export function terminalSocketUrl(loc = window.location, sessionId = null) {
  const u = new URL(`${BASE}/terminal/ws`, loc.href);
  u.protocol = (loc.protocol === 'https:' || u.protocol === 'https:') ? 'wss:' : 'ws:';
  if (sessionId) u.searchParams.set('session', sessionId);
  return u.toString();
}

/**
 * Whether the terminal backend is available and what it is running.
 */
export function terminalStatus() {
  return request('/terminal/status');
}

/**
 * Kills EVERY session (backs Settings' "Restart terminal" full reset).
 */
export function killTerminal() {
  return request('/terminal/kill', { method: 'POST' });
}

/**
 * Server-side session list — the source of truth the tab strip reconciles
 * against.
 *
 * @returns {Promise<{sessions: Array<{id: string, name: string, alive: boolean, createdAt: number, cwd: string}>, max: number}>}
 */
export function listTerminalSessions() {
  return request('/terminal/sessions');
}

/**
 * Starts a new terminal session and returns its record.
 */
export function createTerminalSession() {
  return request('/terminal/sessions', { method: 'POST' });
}

/**
 * Kills one session, leaving the others alive.
 */
export function killTerminalSession(id) {
  return request(`/terminal/sessions/${encodeURIComponent(id)}/kill`, { method: 'POST' });
}

/**
 * Verify which detected path tokens are real files (the backend resolves them
 * against the shell's live cwd).
 *
 * @returns {Promise<Array<{input: string, abs: string, exists: boolean}>>}
 */
export function resolveTerminalPaths(paths, sessionId = null) {
  return request('/terminal/resolve', {
    method: 'POST',
    body: JSON.stringify(sessionId ? { paths, session: sessionId } : { paths }),
  }).then((r) => r.resolved || []);
}

/**
 * Open an already-resolved absolute path in the user's editor at line[:col].
 */
export function openInEditor(path, line, col, sessionId = null) {
  return request('/terminal/open', {
    method: 'POST',
    body: JSON.stringify(sessionId ? { path, line, col, session: sessionId } : { path, line, col }),
  });
}
