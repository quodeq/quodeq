import { TOOLTIP_CURSOR_OFFSET, TOOLTIP_EST_W, TOOLTIP_EST_H } from './galaxyTunables.js';

/**
 * Place a hover tooltip just off the cursor, pulled back so its estimated
 * box stays inside the viewport. Shared by the dimension galaxy and the
 * folder galaxy so both tooltips clamp the same way.
 *
 * @param {number} x - Cursor client X
 * @param {number} y - Cursor client Y
 * @param {number} vw - Viewport width
 * @param {number} vh - Viewport height
 * @returns {{ left: number, top: number }} CSS pixel offsets
 */
export function clampTooltipToViewport(x, y, vw, vh) {
  return {
    left: Math.min(x + TOOLTIP_CURSOR_OFFSET, vw - TOOLTIP_EST_W),
    top: Math.min(y + TOOLTIP_CURSOR_OFFSET, vh - TOOLTIP_EST_H),
  };
}
