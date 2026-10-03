// The document icon used for files in the Map, as numbers both renderers
// share: the SVG FileShape builds path strings from these, the canvas
// renderer traces them directly. Authored at origin (centred on 0,0) in a
// BASE-unit box and scaled to the circle radius by the caller.

export const FILE_SHAPE_BASE = 20;
// Page proportions and the dog-eared corner, as fractions of BASE.
const WIDTH_RATIO = 0.7, HEIGHT_RATIO = 0.9, FOLD_RATIO = 0.25;
// The three rule lines: how far in from each edge they start and end, and
// how far down the page each one sits. All fractions of the page box.
const LINE_LEFT_RATIO = 0.2, LINE_RIGHT_RATIO = 0.8;
const LINE_TOP_RATIO = 0.38, LINE_MID_RATIO = 0.54, LINE_BOTTOM_RATIO = 0.70;
// The bottom line is drawn short, as if the text ran out.
const LINE_BOTTOM_LENGTH_RATIO = 0.85;

export const FILE_W = FILE_SHAPE_BASE * WIDTH_RATIO;
export const FILE_H = FILE_SHAPE_BASE * HEIGHT_RATIO;
export const FILE_X = -FILE_W / 2;
export const FILE_Y = -FILE_H / 2;
export const FILE_FOLD = FILE_W * FOLD_RATIO;
export const FILE_CORNER_RX = 1.5;

// Stroke widths in screen pixels; divide by the total scale to keep them crisp.
export const FILE_BODY_STROKE_PX = 0.8;
export const FILE_FOLD_STROKE_PX = 0.5;

export const FILE_FILL_OPACITY = 0.85;
export const FILE_FOLD_OPACITY = 0.5;
export const FILE_LINE_OPACITY_PRIMARY = 0.4;
export const FILE_LINE_OPACITY_SECONDARY = 0.3;

const LX1 = FILE_X + FILE_W * LINE_LEFT_RATIO;
const LX2 = FILE_X + FILE_W * LINE_RIGHT_RATIO;

/** The rule lines as `[x1, y, x2, opacity]`, top to bottom. */
export const FILE_RULE_LINES = [
  [LX1, FILE_Y + FILE_H * LINE_TOP_RATIO, LX2, FILE_LINE_OPACITY_PRIMARY],
  [LX1, FILE_Y + FILE_H * LINE_MID_RATIO, LX2, FILE_LINE_OPACITY_PRIMARY],
  [LX1, FILE_Y + FILE_H * LINE_BOTTOM_RATIO, LX2 * LINE_BOTTOM_LENGTH_RATIO, FILE_LINE_OPACITY_SECONDARY],
];

/** Colour of the rule lines: white at the given opacity, like the SVG. */
export function ruleLineColor(opacity) {
  return `rgba(255,255,255,${opacity})`;
}
