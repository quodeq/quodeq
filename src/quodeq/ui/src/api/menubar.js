/**
 * Menu bar icon API — the built-in macOS menu bar feature's Settings toggle.
 */

import { request } from './request.js';

export function getMenubar() {
  return request('/menubar');
}

export function setMenubar(enabled) {
  return request('/menubar', { method: 'PUT', body: JSON.stringify({ enabled }) });
}
