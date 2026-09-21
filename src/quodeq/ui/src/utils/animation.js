/**
 * Shared animation helpers for list entry effects.
 */

/**
 * The inline style that staggers a list item's entry animation by its
 * position, capped so a long list's tail does not sit waiting to appear.
 *
 * @param {number} index Position of the item in the list.
 * @param {number} perItemMs Delay added per position.
 * @param {number} maxMs Longest delay any item may take.
 * @returns {{animationDelay: string}}
 */
export function staggerDelayStyle(index, perItemMs, maxMs) {
  return { animationDelay: `${Math.min(index * perItemMs, maxMs)}ms` };
}
