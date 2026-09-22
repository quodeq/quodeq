/**
 * Menu bar icon API — the built-in macOS menu bar feature's Settings toggle.
 */

import { request } from './request.js';

/**
 * Whether the menu bar icon is currently enabled.
 */
export function getMenubar() {
  return request('/menubar');
}

/**
 * Turns the menu bar icon on or off.
 */
export function setMenubar(enabled) {
  return request('/menubar', { method: 'PUT', body: JSON.stringify({ enabled }) });
}
