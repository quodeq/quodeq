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
