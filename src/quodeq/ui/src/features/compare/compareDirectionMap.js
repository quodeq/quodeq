/**
 * Pixel geometry for the fleet's direction map, kept pure so it is testable
 * without a browser. A quadrant chart: the vertical axis is 0 movement and
 * sits in the exact centre, the horizontal axis is the fleet average, so
 * they cross mid-plot. Up is score, right is 30-day improvement, dot size
 * is files (how much code that score covers, never a verdict).
 *
 * Projects with no runs in the window have no direction to plot: they are
 * returned as `still`, not parked on 0 (which would claim "steady").
 */
const HALF_STEP = 0.5;
// Movement within ±STEADY points in 30 days counts as holding steady.
export const STEADY = 0.3;
const MIN_R = 4;
const MAX_R = 15;
// The score range reaches this far past the furthest project.
const REACH_PAD = 0.4;
// Ticks closer than this to the fleet average would sit on its axis line.
const TICK_CLEARANCE = 0.3;
// Label boxes: estimated glyph width and line height (px).
const CHAR_W = 6.2;
const LINE_H = 12;
const LABEL_GAP = 4;
const LABEL_BASELINE = 3.5;
const MAX_LABEL_STEPS = 3;
// The stale tag adds " · stale" after the name.
const STALE_TAG_CHARS = 8;

function scales(moving, rows, fleetScore, box) {
  // Half-point steps, at least ±1, so the ticks land on round numbers.
  const span = Math.max(1, Math.ceil(Math.max(0, ...moving.map((r) => Math.abs(r.delta))) * 2 + 1) / 2);
  const reach = Math.max(1, ...rows.map((r) => Math.abs(r.score - fleetScore))) + REACH_PAD;
  const x = (d) => box.left + ((d + span) / (2 * span)) * box.width;
  const y = (v) => box.top + (1 - (v - (fleetScore - reach)) / (2 * reach)) * box.height;
  return { span, reach, x, y };
}

function ticksFor(sc, fleetScore) {
  const score = [];
  for (let v = Math.ceil(fleetScore - sc.reach); v <= fleetScore + sc.reach; v += 1) {
    if (Math.abs(v - fleetScore) > TICK_CLEARANCE) score.push({ v, y: sc.y(v) });
  }
  // Round steps: whole points on a wide span, halves on a narrow one.
  const step = sc.span > 2 ? 1 : HALF_STEP;
  const move = [];
  for (let d = step; d <= sc.span; d += step) move.push({ d: -d, x: sc.x(-d) }, { d, x: sc.x(d) });
  return { score, move };
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
  const moving = rows.filter((r) => r.delta != null && r.score != null);
  const still = rows.filter((r) => r.delta == null && r.score != null);
  const sc = scales(moving, rows.filter((r) => r.score != null), fleetScore, box);
  const maxFiles = Math.max(1, ...rows.map((r) => r.totalFiles || 0));
  const points = moving
    .map((row) => ({
      row,
      cx: sc.x(row.delta),
      cy: sc.y(row.score),
      r: MIN_R + (MAX_R - MIN_R) * Math.sqrt((row.totalFiles || 0) / maxFiles),
    }))
    .sort((a, b) => b.r - a.r);
  placeLabels(points, box);
  return {
    points,
    still,
    center: { x: sc.x(0), y: sc.y(fleetScore) },
    steady: { x1: sc.x(-STEADY), x2: sc.x(STEADY) },
    ticks: ticksFor(sc, fleetScore),
  };
}
