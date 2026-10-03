/**
 * Server log API — the Settings server-log tail.
 */

import { request } from './request.js';

/**
 * Log lines after the `since` cursor, or the recent tail when `since` < 0.
 *
 * @param {number} since - Index of the last line already seen, or -1.
 * @param {{signal?: AbortSignal, timeout?: number}} [options]
 * @returns {Promise<{lines: Array<{index: number, timestamp?: string, line: string}>}>}
 */
export function getServerLogs(since, { signal, timeout } = {}) {
  const qs = since >= 0 ? `?since=${since}` : '';
  return request(`/logs${qs}`, { signal, timeout });
}
