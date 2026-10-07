/**
 * Selection for LiveFindingsTicker: the latest findings across every
 * dimension, newest first.
 */

export const TICKER_SIZE = 10;
export const MAX_PINNED = 3;

// Rows from before the stream stamped `arrivalSeq` fall back to their place
// in their own dimension's list, which still keeps each dimension in order.
const arrivalOrder = (v, i) => v.arrivalSeq ?? i;

/**
 * Each dimension's list is already in arrival order, so only its tail can
 * make the cut. That keeps the cost at `size` rows per dimension however
 * many findings the run has.
 *
 * @param {Record<string, Array>} liveViolations
 * @param {number} [size]
 * @returns {Array<{key: string, dim: string, v: Object}>}
 */
export function latestFindings(liveViolations, size = TICKER_SIZE) {
  const tail = [];
  for (const [dim, vs] of Object.entries(liveViolations ?? {})) {
    const list = vs ?? [];
    for (let i = Math.max(0, list.length - size); i < list.length; i++) {
      tail.push({ key: findingKey(dim, list[i], i), dim, v: list[i], order: arrivalOrder(list[i], i) });
    }
  }
  return tail
    .sort((a, b) => b.order - a.order)
    .slice(0, size)
    .map(({ key, dim, v }) => ({ key, dim, v }));
}

export function findingKey(dim, v, i) {
  return `${dim}-${v.arrivalSeq ?? `i${i}`}-${v.file}-${v.principle}-${String(v.line ?? '')}`;
}

export function countFindings(liveViolations) {
  return Object.values(liveViolations ?? {}).reduce((n, vs) => n + (vs?.length ?? 0), 0);
}

/** Pin a ticker row, newest pin first, dropping the oldest past the cap. */
export function addPin(pins, item, max = MAX_PINNED) {
  if (pins.some((p) => p.key === item.key)) return pins;
  return [item, ...pins].slice(0, max);
}
