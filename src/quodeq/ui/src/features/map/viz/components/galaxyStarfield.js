/**
 * The background star field both galaxy canvases draw.
 *
 * The galaxy view and the folder view render different scenes but share the
 * same backdrop: a field of pre-seeded stars twinkling between two alphas in
 * the muted text colour. Kept in its own module so neither draw module has to
 * import the other.
 */
import { TAU } from '../core/galaxyCore.js';
import { BACKGROUND } from './galaxyTuning.js';

/**
 * Draw the background star field.
 *
 * @param {CanvasRenderingContext2D} ctx
 * @param {Array<{x: number, y: number, sz: number, sp: number, tw: number}>} bg
 *   Background stars in unit coordinates (see mkBackgroundStars).
 * @param {Object} tc Theme colours, as returned by getThemeColors.
 * @param {{W: number, H: number, t: number}} frame Canvas size and scene clock.
 */
export function drawStarfield(ctx, bg, tc, frame) {
  const { W, H, t } = frame;
  const { r: mr, g: mg, b: mb } = tc.textMuted;
  bg.forEach(s => {
    const a = BACKGROUND.starAlphaBase + BACKGROUND.starAlphaAmp * Math.sin(t * s.sp + s.tw);
    ctx.beginPath(); ctx.arc(s.x * W, s.y * H, s.sz, 0, TAU);
    ctx.fillStyle = `rgba(${mr},${mg},${mb},${a})`; ctx.fill();
  });
}
