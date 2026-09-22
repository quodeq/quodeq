/**
 * Severity ring cues for the galaxy folder view, batched per frame.
 *
 * Every violation particle carries a shape cue so severity does not ride on
 * colour alone (U-ACC-2, 6423). Drawn one particle at a time that is a
 * beginPath/arc/stroke plus two style writes per particle per frame, and a
 * folder view holds hundreds of particles. So the arcs are collected instead
 * and stroked as one path per group, with the style written once per group.
 *
 * The group key is severity, ring index and line width. Severity because the
 * colour is a pure function of it (sevRGB), ring index to keep critical's two
 * concentric rings apart, and line width because it tracks the particle size
 * once zoom lifts it off its floor: grouping on it keeps the pixels identical
 * instead of picking one width for a whole severity.
 */
import { TAU, rgba } from '../core/galaxyCore.js';

const CUE_RING_RADIUS_RATIO = 2.2; // ring sits outside the particle's own dot
const CUE_RING2_RADIUS_RATIO = 3.4; // critical's second, outer ring
const CUE_RING_WIDTH_RATIO = 0.25;
const CUE_RING_WIDTH_MIN = 0.6;
const CUE_RING_MIN_RADIUS = 1.6; // px, keeps the cue readable zoomed out
const CUE_RING_GAP_MIN = 1.4; // px, keeps critical's two rings apart
const CUE_MIN_PARTICLE_SIZE = 0.15; // what drawParticles itself paints down to
const CUE_ALPHA = 0.9;
const ARC_STRIDE = 3; // x, y, r per queued arc

/**
 * Shape cue for a violation particle's severity, so severity does not ride
 * on colour alone (U-ACC-2). The three differ by outline, not brightness:
 * 'double-ring' for critical, 'ring' for major, 'dot' (the plain dot
 * drawParticles already paints) for minor and anything else.
 */
export function starShapeFor(severity) {
  switch (severity) {
    case 'critical': return 'double-ring';
    case 'major': return 'ring';
    default: return 'dot';
  }
}

/** A collector for one frame's severity ring arcs. */
export function newCueBatch() {
  return new Map();
}

/**
 * Queue one particle's ring arcs, at the orbit position drawParticles paints
 * it at (same angle/scale math as galaxyCore's). Nothing is drawn here.
 *
 * `p` is a particle in the compact schema galaxyCore's mkParticles emits:
 * `os` orbit speed, `op` orbit phase, `or` orbit radius, `ec` eccentricity
 * (x only, so the orbit reads as a tilted ellipse), `sz` size, `sev`
 * severity, `col` colour. The names are short because a frame walks
 * thousands of these.
 *
 * @param {Map} batch - the frame's collector, keyed severity|ring|width.
 * @param {object} p - the particle.
 * @param {{x: number, y: number}} sc - its star's screen centre.
 * @param {number} scale - world-to-screen zoom.
 * @param {number} t - the frame's time, which advances the orbit.
 */
export function collectSeverityCue(batch, p, sc, scale, t) {
  const shape = starShapeFor(p.sev);
  const size = p.sz * scale;
  if (shape === 'dot' || size < CUE_MIN_PARTICLE_SIZE) return;
  const angle = t * p.os + p.op;
  const px = sc.x + Math.cos(angle) * p.or * p.ec * scale;
  const py = sc.y + Math.sin(angle) * p.or * scale;
  const inner = Math.max(size * CUE_RING_RADIUS_RATIO, CUE_RING_MIN_RADIUS);
  const radii = shape === 'double-ring'
    ? [inner, Math.max(size * CUE_RING2_RADIUS_RATIO, inner + CUE_RING_GAP_MIN)]
    : [inner];
  const lineWidth = Math.max(CUE_RING_WIDTH_MIN, size * CUE_RING_WIDTH_RATIO);
  radii.forEach((r, ring) => {
    const key = `${p.sev}|${ring}|${lineWidth}`;
    let group = batch.get(key);
    if (!group) {
      // One rgba() string per group per frame instead of one per particle.
      group = { strokeStyle: rgba(p.col, CUE_ALPHA), lineWidth, arcs: [] };
      batch.set(key, group);
    }
    group.arcs.push(px, py, r);
  });
}

/** Stroke every queued group: one path, one style pair and one stroke each. */
export function drawCueBatch(ctx, batch) {
  batch.forEach(({ strokeStyle, lineWidth, arcs }) => {
    ctx.strokeStyle = strokeStyle;
    ctx.lineWidth = lineWidth;
    ctx.beginPath();
    for (let i = 0; i < arcs.length; i += ARC_STRIDE) {
      const x = arcs[i], y = arcs[i + 1], r = arcs[i + 2];
      // Without the moveTo the arc is joined to the previous one by a line.
      ctx.moveTo(x + r, y);
      ctx.arc(x, y, r, 0, TAU);
    }
    ctx.stroke();
  });
}
