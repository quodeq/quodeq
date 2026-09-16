/**
 * galaxyTunables.js: the numbers that shape the galaxy visualizations
 * (zoom breakpoints, tooltip placement, default canvas box). Named here,
 * next to galaxyCore.js, so the draw, event and hook modules read one
 * value and a tweak lands in one place.
 */

// Camera zoom past which principle planets appear around a dimension star
// and the dimension-level decorations start fading out.
export const ZOOM_DIMENSION_LEVEL = 1.5;
// Camera zoom past which the selected principle's violation orbs take over
// from its particles and the sibling principles' labels.
export const ZOOM_PRINCIPLE_LEVEL = 12;

// Tooltip offset from the cursor, and the box it is assumed to occupy when
// it is clamped inside the viewport (the element sizes to content, so these
// are a generous estimate, not a measurement).
export const TOOLTIP_CURSOR_OFFSET = 16;
export const TOOLTIP_EST_W = 200;
export const TOOLTIP_EST_H = 160;

// Canvas box used before the ResizeObserver reports the real one, and the
// world-space box scenes are laid out in.
export const DEFAULT_CANVAS_W = 800;
export const DEFAULT_CANVAS_H = 600;
