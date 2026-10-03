import { withinRadius } from './hitTest.js';
import { PACK_BASE_SIZE } from './packLayout.js';

// The SVG view box the pack is authored in: a PAD margin around BASE_SIZE
// layout units, fitted to the container with the aspect ratio kept
// (xMidYMid meet). The canvas reproduces the same mapping so the two
// renderers place every circle identically.
export const PACK_VIEW_PAD = 20;
const VIEW_SPAN = PACK_BASE_SIZE + PACK_VIEW_PAD * 2;

/** Pixels per layout unit and the pixel origin of the view box. */
export function packViewport(width, height) {
  const scale = Math.min(width, height) / VIEW_SPAN;
  return {
    scale,
    ox: (width - VIEW_SPAN * scale) / 2 + PACK_VIEW_PAD * scale,
    oy: (height - VIEW_SPAN * scale) / 2 + PACK_VIEW_PAD * scale,
  };
}

/** Circles after the focus transform, in layout units. */
export function screenCoordsFor(circles, { k, tx, ty }) {
  return circles.map((c) => ({ cx: c.x * k + tx, cy: c.y * k + ty, r: c.r * k }));
}

/** Container pixel to layout units. */
export function toLayoutPoint(px, py, viewport) {
  return { x: (px - viewport.ox) / viewport.scale, y: (py - viewport.oy) / viewport.scale };
}

/** Index of the deepest circle under a layout point, or null. Circles nest,
 * so the smallest one containing the point is the one on top. The root
 * (index of depth 0) is never a hit: clicking it is a background click. */
export function hitCircle(circles, screenCoords, x, y) {
  let best = null;
  for (let i = 0; i < circles.length; i++) {
    if (circles[i].depth === 0) continue;
    const sc = screenCoords[i];
    if (!withinRadius(x, y, sc.cx, sc.cy, sc.r)) continue;
    if (best === null || sc.r < screenCoords[best].r) best = i;
  }
  return best;
}

/** Whether a circle touches the canvas. Culling is against the canvas
 * pixels, not the square view box: a wide or tall canvas shows content in
 * the letterbox either side of the box (the SVG view clips to its element
 * too), and after zooming in the siblings of the focused folder live there.
 * Sub-pixel circles are kept: the 1px stroke still paints them, and that
 * texture is what makes a zoomed-out folder read as full rather than empty
 * (the SVG view gets the same from its non-scaling stroke). */
export function isDrawable(sc, viewport, width, height) {
  const px = viewport.ox + sc.cx * viewport.scale;
  const py = viewport.oy + sc.cy * viewport.scale;
  const r = sc.r * viewport.scale;
  return px + r > 0 && px - r < width && py + r > 0 && py - r < height;
}
