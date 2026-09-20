import {
  TAU, getThemeColors, drawGlow, drawParticles, rgba,
} from '../core/galaxyCore.js';
import { ZOOM_DIMENSION_LEVEL, ZOOM_PRINCIPLE_LEVEL, CANVAS_FONT_FAMILY } from '../core/galaxyTunables.js';
import { drawStarfield } from './galaxyStarfield.js';
import {
  BACKGROUND, STAR, VIOLATION_ORBS, MIN_VISIBLE_ALPHA, LABEL_ALPHA,
  FOCUS_RING, FOCUS_RING_DASH, UNFOCUSED_CLUSTER_MIN_ALPHA, DIM_FADE_SPAN,
  CONSTELLATION, CONSTELLATION_RING_DASH, CONSTELLATION_LINE_DASH,
  DIM_PARTICLE, DIM_LABEL, PRINCIPLE,
} from './galaxyTuning.js';

// Dimension labels grow with the zoom up to this cap. Deliberately equal
// to ZOOM_DIMENSION_LEVEL: once principles appear the label stops growing.
const LABEL_SCALE_CAP = ZOOM_DIMENSION_LEVEL;
// Zoom units past ZOOM_PRINCIPLE_LEVEL over which the selected principle's
// particles and label hand off to its violation orbs, which fade in over
// the same span.
const PRINCIPLE_FADE_SPAN = 20;
// The other principles' labels get out of the way faster than that.
const SIBLING_LABEL_FADE_SPAN = 15;

/**
 * Render one animation frame on the galaxy canvas.
 *
 * @param {CanvasRenderingContext2D} ctx - Canvas 2D context
 * @param {object} scene - The scene built by buildScene
 * @param {object} cam - Current camera { x, y, z }
 * @param {object} nav - Current navigation state { depth, dim, prin, clusterCx, clusterCy }
 * @param {object} opts - Drawing options
 * @param {number} opts.W - Canvas width
 * @param {number} opts.H - Canvas height
 * @param {number} opts.t - Current time
 * @param {number} opts.mx - Mouse x (screen coords, -1 when off-canvas)
 * @param {number} opts.my - Mouse y (screen coords, -1 when off-canvas)
 * @param {boolean} opts.showLabels - Whether to show text labels
 * @param {boolean} opts.animating - Whether an animation transition is active
 * @param {number|null} opts.rDim - Render dimension index (accounts for zoom-out prev state)
 * @param {number|null} opts.rPrin - Render principle index (accounts for zoom-out prev state)
 * @param {Function} opts.w2s - World-to-screen transform (wx, wy) => { x, y }
 * @param {HTMLElement} opts.parentEl - Parent element for theme color resolution
 * @returns {{ hovered: object|null }} - Hovered element info for hit testing
 */
export function drawFrame(ctx, scene, cam, nav, opts) {
  const tc = getThemeColors(opts.parentEl);

  drawBackground(ctx, scene, opts, tc);
  drawConstellations(ctx, scene, { cam, nav }, opts, tc);
  const dimHovered = drawDimStars(ctx, scene, { cam, nav }, opts, tc);
  const prinHovered = drawPrinciples(ctx, scene, { cam, nav }, opts, tc);
  drawZoomedPrinciple(ctx, scene, cam, opts);

  return { hovered: prinHovered ?? dimHovered };
}

/** Phase 1: radial gradient background + background star field. */
function drawBackground(ctx, scene, opts, tc) {
  const { W, H } = opts;
  const grad = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, Math.max(W, H) * BACKGROUND.gradientRadiusFraction);
  grad.addColorStop(0, tc.bgAlt); grad.addColorStop(1, tc.bg);
  ctx.fillStyle = grad; ctx.fillRect(0, 0, W, H);
  drawStarfield(ctx, scene.bg, tc, opts);
}

/** Phase 2: constellation dashed circles, lines, and labels (galaxy level only). */
function drawConstellations(ctx, scene, view, opts, tc) {
  const { cam, nav } = view;
  const { w2s, showLabels, W, H } = opts;
  const { r: mr, g: mg, b: mb } = tc.textMuted;
  if (cam.z >= CONSTELLATION.hideAtZoom) return;
  const conAlpha = Math.max(0, 1 - (cam.z - 1) / 2);
  (scene.constellations || []).forEach(con => {
    const isFocused = nav.clusterCx == null || (con.cx === nav.clusterCx && con.cy === nav.clusterCy);
    const conClusterDim = isFocused ? 1 : Math.max(UNFOCUSED_CLUSTER_MIN_ALPHA, 1 - (cam.z - 1) / 2);
    // Dashed circle around cluster
    const csc = w2s(W / 2 + con.cx, H / 2 + con.cy);
    const circleR = (con.spread + 10) * cam.z;
    ctx.beginPath(); ctx.arc(csc.x, csc.y, circleR, 0, TAU);
    ctx.strokeStyle = `rgba(${mr},${mg},${mb},${CONSTELLATION.ringAlpha * conAlpha * conClusterDim})`;
    ctx.lineWidth = 1;
    ctx.setLineDash(CONSTELLATION_RING_DASH); ctx.stroke(); ctx.setLineDash([]);

    // Constellation lines between stars
    con.lines.forEach(l => {
      const sa = w2s(scene.stars[l.a].x, scene.stars[l.a].y);
      const sb = w2s(scene.stars[l.b].x, scene.stars[l.b].y);
      ctx.beginPath(); ctx.moveTo(sa.x, sa.y); ctx.lineTo(sb.x, sb.y);
      ctx.strokeStyle = `rgba(${mr},${mg},${mb},${CONSTELLATION.lineAlpha * conAlpha * conClusterDim})`;
      ctx.lineWidth = CONSTELLATION.lineWidthPx;
      ctx.setLineDash(CONSTELLATION_LINE_DASH); ctx.stroke(); ctx.setLineDash([]);
    });
    // Constellation label — above the dashed circle
    if (showLabels && con.label) {
      const lx = csc.x;
      const ly = csc.y - circleR - 10;
      ctx.font = `600 ${CONSTELLATION.labelFontPx}px ${CANVAS_FONT_FAMILY}`;
      ctx.textAlign = 'center';
      ctx.fillStyle = `rgba(${mr},${mg},${mb},${CONSTELLATION.labelAlpha * conAlpha * conClusterDim})`;
      ctx.fillText(con.label, lx, ly);
      con._lx = lx; con._ly = ly;
    }
  });
}

/**
 * Phase 3: dimension stars with principle particles, glow, labels, and hit-test.
 * Returns the currently hovered element (or null).
 */
/** Orbiting principle particles around one dimension star (part of phase 3).
 * `orbit` is { sc, cam, t, particleAlpha }: the star's screen centre and the
 * frame's camera/time/fade. */
function drawDimParticles(ctx, principles, orbit) {
  const { sc, cam, t, particleAlpha } = orbit;
  if (particleAlpha <= MIN_VISIBLE_ALPHA) return;
  (principles || []).forEach(p => {
    const dp = p.dimParticle;
    const a = t * dp.os + dp.op;
    const px = sc.x + Math.cos(a) * dp.or * dp.ec * cam.z;
    const py = sc.y + Math.sin(a) * dp.or * cam.z;
    const tw = DIM_PARTICLE.twinkleBase + DIM_PARTICLE.twinkleAmp * Math.sin(t * DIM_PARTICLE.twinkleSpeed + dp.tp);
    const sz = dp.sz * cam.z;
    if (sz > DIM_PARTICLE.minSizePx) {
      const { r, g, b } = dp.col;
      ctx.beginPath(); ctx.arc(px, py, sz * DIM_PARTICLE.haloRatio, 0, TAU);
      ctx.fillStyle = `rgba(${r},${g},${b},${tw * DIM_PARTICLE.haloAlpha * particleAlpha})`; ctx.fill();
      ctx.beginPath(); ctx.arc(px, py, sz, 0, TAU);
      ctx.fillStyle = `rgba(${r},${g},${b},${(tw + DIM_PARTICLE.coreAlphaBoost) * particleAlpha})`; ctx.fill();
    }
  });
}

/** Draws one dimension star (glow, label, focus ring) and returns hover info when hit. */
function drawOneDimStar(ctx, target, view, opts, tc) {
  const { scene, s, i } = target;
  const { cam, nav } = view;
  const { t, mx, my, showLabels, animating, rDim, w2s } = opts;
  const sc = w2s(s.x, s.y);
  const pulse = 1 + STAR.pulseAmplitude * Math.sin(t * STAR.pulseSpeed + s.pp);
  const isSelected = rDim === i;
  const sr = s.radius * pulse * cam.z * STAR.screenRadiusFraction;
  // Dim stars not in the focused cluster
  const inFocusedCluster = nav.clusterCx == null || (s._clusterCx === nav.clusterCx && s._clusterCy === nav.clusterCy);
  const clusterDim = inFocusedCluster ? 1 : Math.max(UNFOCUSED_CLUSTER_MIN_ALPHA, 1 - (cam.z - 1) / 2);
  // All dim-level decorations fade out once we zoom past galaxy level
  const dimFade = isSelected ? 1 : Math.max(0, 1 - (cam.z - ZOOM_DIMENSION_LEVEL) / DIM_FADE_SPAN) * clusterDim;

  // Principle particles orbiting this dimension — fade out as principle planets fade in
  const particleAlpha = isSelected ? Math.max(0, 1 - (cam.z - ZOOM_DIMENSION_LEVEL) / 2) : dimFade;
  drawDimParticles(ctx, scene.principles[i], { sc, cam, t, particleAlpha });

  drawGlow(ctx, { x: sc.x, y: sc.y, r: sr, col: s.col, alpha: isSelected ? clusterDim : dimFade });
  // Hide dimension label when zoomed past galaxy level
  const labelAlpha = isSelected ? Math.max(0, 1 - (cam.z - ZOOM_DIMENSION_LEVEL) / 2) : dimFade;
  if (showLabels && labelAlpha > MIN_VISIBLE_ALPHA) {
    const fs = Math.min(cam.z, LABEL_SCALE_CAP);
    ctx.font = `600 ${Math.max(DIM_LABEL.fontMinPx, DIM_LABEL.fontPx * fs)}px ${CANVAS_FONT_FAMILY}`;
    ctx.textAlign = 'center'; ctx.fillStyle = rgba(tc.text, LABEL_ALPHA * labelAlpha);
    ctx.fillText(s.name, sc.x, sc.y - sr - DIM_LABEL.offsetPx * fs);
    ctx.font = `${Math.max(DIM_LABEL.scoreFontMinPx, DIM_LABEL.scoreFontPx * fs)}px ${CANVAS_FONT_FAMILY}`;
    ctx.fillStyle = rgba(tc.textMuted, DIM_LABEL.scoreAlpha * labelAlpha);
    ctx.fillText(s.score.toFixed(1), sc.x, sc.y + sr + DIM_LABEL.scoreOffsetPx * fs);
  }
  // Keyboard focus ring (a11y, #675) — drawn at the dim's hit radius so it
  // lines up with where Enter activates.
  if (nav.depth === 0 && opts.focusedIdx === i) {
    drawFocusRing(ctx, sc.x, sc.y, Math.max(sr * 2, DIM_LABEL.hitRadiusMinPx) + FOCUS_RING.padPx, tc);
  }
  if (!animating && nav.depth === 0 && mx >= 0) {
    const dx = mx - sc.x, dy = my - sc.y;
    const hitR = Math.max(sr * 2, DIM_LABEL.hitRadiusMinPx);
    if (dx * dx + dy * dy < hitR * hitR) return { type: 'dim', idx: i, data: s };
  }
  return null;
}

function drawDimStars(ctx, scene, view, opts, tc) {
  let newHovered = null;
  scene.stars.forEach((s, i) => {
    const hit = drawOneDimStar(ctx, { scene, s, i }, view, opts, tc);
    if (hit) newHovered = hit;
  });
  return newHovered;
}

/** Dashed ring marking the keyboard-focused node (a11y, #675). */
function drawFocusRing(ctx, cx, cy, r, tc) {
  ctx.save();
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, TAU);
  ctx.strokeStyle = rgba(tc.text, FOCUS_RING.alpha);
  ctx.lineWidth = 2;
  ctx.setLineDash(FOCUS_RING_DASH);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.restore();
}

/**
 * Phase 4: principle planets visible when zoomed into a dimension.
 * Returns the hovered principle element, or null.
 */
function drawPrinciples(ctx, scene, view, opts, tc) {
  const { cam, nav } = view;
  const { t, mx, my, showLabels, animating, w2s, rDim } = opts;
  if (!(cam.z > ZOOM_DIMENSION_LEVEL && rDim !== null)) return null;
  const dim = scene.stars[rDim];
  const dsc = w2s(dim.x, dim.y);
  const pAlpha = Math.min(1, (cam.z - ZOOM_DIMENSION_LEVEL) / DIM_FADE_SPAN);
  const pScale = cam.z * PRINCIPLE.scaleFraction;
  let newHovered = null;
  (scene.principles[rDim] || []).forEach((p, pi) => {
    const isSelectedPrin = nav.prin === pi;
    const sc = w2s(p.x, p.y);
    const sr = p.radius * pScale;
    // orbit ring
    ctx.beginPath(); ctx.arc(dsc.x, dsc.y, Math.hypot(sc.x - dsc.x, sc.y - dsc.y), 0, TAU);
    ctx.strokeStyle = `rgba(50,55,80,${PRINCIPLE.orbitRingAlpha * pAlpha})`; ctx.lineWidth = 0.5; ctx.stroke();
    // connection line
    ctx.beginPath(); ctx.moveTo(dsc.x, dsc.y); ctx.lineTo(sc.x, sc.y);
    ctx.strokeStyle = rgba(dim.col, PRINCIPLE.linkAlpha * pAlpha); ctx.lineWidth = PRINCIPLE.linkWidthPx; ctx.stroke();
    // Violation/compliance particles — fade out on selected (large orbs take over), shrink on others
    const particleFade = isSelectedPrin ? Math.max(0, 1 - (cam.z - ZOOM_PRINCIPLE_LEVEL) / PRINCIPLE_FADE_SPAN) : 1;
    // Non-selected: smaller particles but keep orbit wide so they don't collide with planet
    const cappedScale = Math.min(
      PRINCIPLE.siblingScaleCap,
      PRINCIPLE.siblingReferenceZoom * PRINCIPLE.scaleFraction / Math.max(pScale, PRINCIPLE.scaleDivisorFloor),
    );
    const particleDrawScale = isSelectedPrin ? pScale * PRINCIPLE.selectedParticleScale : pScale * cappedScale;
    const particleOrbitScale = isSelectedPrin ? pScale * PRINCIPLE.selectedParticleScale : pScale * Math.max(cappedScale, PRINCIPLE.siblingOrbitScaleMin);
    if (particleFade > MIN_VISIBLE_ALPHA) drawParticles(ctx, p.particles, { cx: sc.x, cy: sc.y, scale: particleOrbitScale, alpha: pAlpha * particleFade, t, drawScale: particleDrawScale });
    drawGlow(ctx, { x: sc.x, y: sc.y, r: sr, col: p.col, alpha: pAlpha });
    // Only fade labels/scores — hide on non-selected when zoomed into a principle
    const prinLabelAlpha = isSelectedPrin ? Math.max(0, 1 - (cam.z - ZOOM_PRINCIPLE_LEVEL) / PRINCIPLE_FADE_SPAN) : (nav.prin !== null ? Math.max(0, 1 - (cam.z - ZOOM_PRINCIPLE_LEVEL) / SIBLING_LABEL_FADE_SPAN) : 1);
    if (showLabels && prinLabelAlpha > MIN_VISIBLE_ALPHA) {
      const la = pAlpha * prinLabelAlpha;
      ctx.font = `600 ${PRINCIPLE.labelFontPx}px ${CANVAS_FONT_FAMILY}`;
      ctx.textAlign = 'center'; ctx.fillStyle = rgba(tc.text, LABEL_ALPHA * la);
      ctx.fillText(p.name, sc.x, sc.y - sr - PRINCIPLE.labelOffsetPx);
      ctx.font = `${PRINCIPLE.scoreFontPx}px ${CANVAS_FONT_FAMILY}`;
      ctx.fillStyle = rgba(tc.textMuted, PRINCIPLE.scoreAlpha * la);
      ctx.fillText(p.score.toFixed(1), sc.x, sc.y + sr + PRINCIPLE.scoreOffsetPx);
    }
    if (nav.depth === 1 && opts.focusedIdx === pi) {
      drawFocusRing(ctx, sc.x, sc.y, sr + PRINCIPLE.hitPadPx + FOCUS_RING.padPx, tc);
    }
    if (!animating && nav.depth === 1 && pAlpha > PRINCIPLE.hitMinAlpha && mx >= 0) {
      const dx = mx - sc.x, dy = my - sc.y;
      const hitR = sr + PRINCIPLE.hitPadPx;
      if (dx * dx + dy * dy < hitR * hitR) newHovered = { type: 'prin', idx: pi, data: p };
    }
  });
  return newHovered;
}

/** Phase 5: violation/compliance orbs when zoomed deeply into a principle. */
function drawZoomedPrinciple(ctx, scene, cam, opts) {
  const { t, showLabels, w2s, rDim, rPrin } = opts;
  if (!(cam.z > ZOOM_PRINCIPLE_LEVEL && rDim !== null && rPrin !== null)) return;
  const prin = scene.principles[rDim][rPrin];
  const psc = w2s(prin.x, prin.y);
  const vAlpha = Math.min(1, (cam.z - ZOOM_PRINCIPLE_LEVEL) / PRINCIPLE_FADE_SPAN);
  const vScale = cam.z * VIOLATION_ORBS.scaleFraction;
  prin.particles.forEach((p) => {
    const a = t * p.os + p.op;
    const px = psc.x + Math.cos(a) * p.or * p.ec * vScale;
    const py = psc.y + Math.sin(a) * p.or * vScale;
    const tw = VIOLATION_ORBS.twinkleBase + VIOLATION_ORBS.twinkleAmp * Math.sin(t * VIOLATION_ORBS.twinkleSpeed + p.tp);
    const sr = p.sz * vScale * VIOLATION_ORBS.radiusFraction;
    drawGlow(ctx, { x: px, y: py, r: sr, col: p.col, alpha: vAlpha * tw });
    if (showLabels && sr > VIOLATION_ORBS.labelMinRadiusPx) {
      const sevName = p.sev.charAt(0).toUpperCase() + p.sev.slice(1);
      const fontPx = Math.max(VIOLATION_ORBS.labelFontMinPx, Math.min(VIOLATION_ORBS.labelFontMaxPx, sr * VIOLATION_ORBS.labelFontRadiusFraction));
      ctx.font = `500 ${fontPx}px ${CANVAS_FONT_FAMILY}`;
      ctx.textAlign = 'center'; ctx.fillStyle = rgba(p.col, VIOLATION_ORBS.labelAlpha * vAlpha);
      ctx.fillText(sevName, px, py - sr - VIOLATION_ORBS.labelOffsetPx);
    }
  });
}
