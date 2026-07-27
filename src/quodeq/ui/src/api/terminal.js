import { request, BASE } from './request.js';

export function terminalSocketUrl(loc = window.location, sessionId = null) {
  const u = new URL(`${BASE}/terminal/ws`, loc.href);
  u.protocol = (loc.protocol === 'https:' || u.protocol === 'https:') ? 'wss:' : 'ws:';
  if (sessionId) u.searchParams.set('session', sessionId);
  return u.toString();
}

export function terminalStatus() {
  return request('/terminal/status');
}

// Kills EVERY session (backs Settings' "Restart terminal" full reset).
export function killTerminal() {
  return request('/terminal/kill', { method: 'POST' });
}

// Server-side session list — the source of truth the tab strip reconciles
// against. Returns { sessions: [{ id, name, alive, createdAt, cwd }], max }.
export function listTerminalSessions() {
  return request('/terminal/sessions');
}

export function createTerminalSession() {
  return request('/terminal/sessions', { method: 'POST' });
}

export function killTerminalSession(id) {
  return request(`/terminal/sessions/${encodeURIComponent(id)}/kill`, { method: 'POST' });
}

// Verify which detected path tokens are real files (backend resolves them
// against the shell's live cwd). Returns [{ input, abs, exists }].
export function resolveTerminalPaths(paths, sessionId = null) {
  return request('/terminal/resolve', {
    method: 'POST',
    body: JSON.stringify(sessionId ? { paths, session: sessionId } : { paths }),
  }).then((r) => r.resolved || []);
}

// Open an already-resolved absolute path in the user's editor at line[:col].
export function openInEditor(path, line, col, sessionId = null) {
  return request('/terminal/open', {
    method: 'POST',
    body: JSON.stringify(sessionId ? { path, line, col, session: sessionId } : { path, line, col }),
  });
}
