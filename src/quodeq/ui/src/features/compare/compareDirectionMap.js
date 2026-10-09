/**
 * Pixel geometry for the fleet's direction map, kept pure so it is testable
 * without a browser. The view fits the projects: both ranges reach just past
 * the furthest project, so the dots fill the plot whichever way the fleet is
 * moving. The two references, 0 movement ("no change") and the fleet
 * average score, are plain lines inside that range, wherever they fall: at
 * the left edge, say, when every project is improving. Up is score, right is
 * 30-day improvement, dot size is files (how much code that score covers,
 * never a verdict).
 *
 * Projects with no runs in the window are plotted too, on the "no change"
 * line and marked `still`, so the renderer can draw them hollow: their
 * position says "no movement measured", not "held steady".
 */
const HALF_STEP = 0.5;
// Movement within ±STEADY points in 30 days counts as holding steady.
export const STEADY = 0.3;
const MIN_R = 4;
const MAX_R = 15;
// Each range reaches this share of its width past the furthest value, and
// at least MIN_PAD points, so edge dots and their labels stay inside.
const PAD_SHARE = 0.12;
const MIN_PAD = 0.25;
// A range never narrower than this, in points, so one project or a fleet
// that barely moved still gets a readable scale.
const MIN_SPAN = 1;
// Above this span the ticks step by whole points, below by halves.
const WHOLE_STEP_SPAN = 4;
// Label boxes: estimated glyph width and line height (px).
const CHAR_W = 6.2;
const LINE_H = 12;
const LABEL_GAP = 4;
const LABEL_BASELINE = 3.5;
const MAX_LABEL_STEPS = 3;
// The stale tag adds " · stale" after the name.
const STALE_TAG_CHARS = 8;
// Tick values are rounded to tenths so float steps print cleanly.
const TENTHS = 10;
const EPSILON = 1e-9;

/** [lo, hi] reaching just past every value, at least MIN_SPAN wide. */
function fitRange(values) {
  let lo = Math.min(...values);
  let hi = Math.max(...values);
  if (hi - lo < MIN_SPAN) {
    const mid = (lo + hi) / 2;
    lo = mid - MIN_SPAN / 2;
    hi = mid + MIN_SPAN / 2;
  }
  const pad = Math.max(MIN_PAD, (hi - lo) * PAD_SHARE);
  return [lo - pad, hi + pad];
}

function ticksIn([lo, hi]) {
  const step = hi - lo > WHOLE_STEP_SPAN ? 1 : HALF_STEP;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + EPSILON; v += step) out.push(Math.round(v * TENTHS) / TENTHS);
  return out;
}

function scales(rows, fleetScore, box) {
  // 0 is always in range: the "no change" line is the reference the
  // still projects sit on, and the corner meanings hang off it.
  const xRange = fitRange([0, ...rows.map((r) => r.delta ?? 0)]);
  const yRange = fitRange([fleetScore, ...rows.map((r) => r.score)]);
  const x = (d) => box.left + ((d - xRange[0]) / (xRange[1] - xRange[0])) * box.width;
  const y = (v) => box.top + (1 - (v - yRange[0]) / (yRange[1] - yRange[0])) * box.height;
  return { x, y, xRange, yRange };
}

/* Try right of the dot, then left, then a line lower, against every label
   already placed; the first free spot wins. */
function placeLabels(points, box) {
  const boxes = [];
  const free = (b) => b.x1 >= box.left && b.x2 <= box.left + box.width
    && !boxes.some((o) => b.x1 < o.x2 && b.x2 > o.x1 && Math.abs(b.y - o.y) < LINE_H);
  for (const p of [...points].sort((a, b) => a.cy - b.cy)) {
    const w = (p.row.name.length + (p.row.stale ? STALE_TAG_CHARS : 0)) * CHAR_W;
    let pick = null;
    for (let step = 0; step <= MAX_LABEL_STEPS && !pick; step += 1) {
      const y = p.cy + LABEL_BASELINE + step * LINE_H;
      const right = { x1: p.cx + p.r + LABEL_GAP, x2: p.cx + p.r + LABEL_GAP + w, y, anchorEnd: false };
      const left = { x1: p.cx - p.r - LABEL_GAP - w, x2: p.cx - p.r - LABEL_GAP, y, anchorEnd: true };
      pick = [right, left].find(free) || null;
    }
    p.label = pick || { x1: p.cx + p.r + LABEL_GAP, y: p.cy + LABEL_BASELINE, anchorEnd: false };
    p.label.x = p.label.anchorEnd ? p.label.x2 : p.label.x1;
    boxes.push(p.label);
  }
}

/**
 * Everything the map draws, in px, for a plot box {left, top, width, height}.
 * Points are ordered largest first so small dots paint on top.
 */
export function buildDirectionMap({ rows, fleetScore, box }) {
  const scored = rows.filter((r) => r.score != null);
  const sc = scales(scored, fleetScore, box);
  const maxFiles = Math.max(1, ...scored.map((r) => r.totalFiles || 0));
  const points = scored
    .map((row) => ({
      row,
      still: row.delta == null,
      cx: sc.x(row.delta ?? 0),
      cy: sc.y(row.score),
      r: MIN_R + (MAX_R - MIN_R) * Math.sqrt((row.totalFiles || 0) / maxFiles),
    }))
    .sort((a, b) => b.r - a.r);
  placeLabels(points, box);
  return {
    points,
    zeroX: sc.x(0),
    fleetY: sc.y(fleetScore),
    steady: { x1: Math.max(box.left, sc.x(-STEADY)), x2: Math.min(box.left + box.width, sc.x(STEADY)) },
    ticks: {
      move: ticksIn(sc.xRange).map((d) => ({ d, x: sc.x(d) })),
      score: ticksIn(sc.yRange).map((v) => ({ v, y: sc.y(v) })),
    },
  };
}
