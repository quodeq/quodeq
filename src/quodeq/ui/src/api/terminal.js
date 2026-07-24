import { request, BASE } from './request.js';

export function terminalSocketUrl(loc = window.location) {
  const u = new URL(`${BASE}/terminal/ws`, loc.href);
  u.protocol = (loc.protocol === 'https:' || u.protocol === 'https:') ? 'wss:' : 'ws:';
  return u.toString();
}

export function terminalStatus() {
  return request('/terminal/status');
}

export function killTerminal() {
  return request('/terminal/kill', { method: 'POST' });
}

// Verify which detected path tokens are real files (backend resolves them
// against the shell's live cwd). Returns [{ input, abs, exists }].
export function resolveTerminalPaths(paths) {
  return request('/terminal/resolve', {
    method: 'POST',
    body: JSON.stringify({ paths }),
  }).then((r) => r.resolved || []);
}

// Open an already-resolved absolute path in the user's editor at line[:col].
export function openInEditor(path, line, col) {
  return request('/terminal/open', {
    method: 'POST',
    body: JSON.stringify({ path, line, col }),
  });
}
