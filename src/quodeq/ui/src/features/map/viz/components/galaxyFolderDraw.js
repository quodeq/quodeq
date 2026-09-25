import {
  TAU, getThemeColors, scoreRGB, rgba,
  drawGlow, drawParticles,
} from '../core/galaxyCore.js';
import { HIT_TARGET_TYPE } from '../core/galaxyHitTypes.js';
import { newCueBatch, collectSeverityCue, drawCueBatch } from './galaxyFolderCues.js';
import { CANVAS_FONT_FAMILY } from '../core/galaxyTunables.js';
import { fillBackgroundGradient } from './galaxyStarfield.js';
import {
  STAR, NEBULA, NEBULA_SCENE_BLOBS, NEBULA_FOLDER_BLOBS,
  VIOLATION_ORBS, LABEL_ALPHA, FOLDER_NEBULA, FOLDER_NEBULA_DASH,
  FOLDER_STAR, FOLDER_LABEL,
} from './galaxyTuning.js';
import { SCORE_SCALE_MAX, PERCENT } from '../../../../constants.js';

export { starShapeFor } from './galaxyFolderCues.js';
// Re-exported so the folder canvas's draw surface stays in one module.
export { drawStarfield } from './galaxyStarfield.js';

/**
 * Paint the canvas background gradient and return the theme colours every
 * other draw helper in this module reads. The scene itself is not consulted:
 * the background depends only on size and theme.
 * @param {CanvasRenderingContext2D} ctx
 * @param {{W: number, H: number, canvasRef: object}} params - frame size plus
 *   the canvas ref the theme colours are resolved against.
 * @returns {{tc: object}} the resolved theme colours.
 */
export function drawScene(ctx, params) {
  const { W, H, canvasRef } = params;
  const tc = getThemeColors(canvasRef.current?.parentElement);
  fillBackgroundGradient(ctx, tc, { W, H });
  return { tc };
}

/**
 * One ring of soft, slowly orbiting texture blobs over a nebula disc. Both
 * nebulas draw the same shape, at their own count, speed, alpha and size.
 *
 * `spec` is NEBULA_SCENE_BLOBS or NEBULA_FOLDER_BLOBS with the frame's `t`
 * merged in. Both colour stops are the same for every blob in a ring, so
 * they are built once rather than per blob.
 */
function drawNebulaBlobs(ctx, spec, centre, radius, col, alpha) {
  const { count, spin, orbit, sizeBase, sizeAmp, wobble, wobbleStep, t } = spec;
  const { r, g, b } = col;
  const innerStop = `rgba(${r},${g},${b},${alpha})`;
  const outerStop = `rgba(${r},${g},${b},0)`;
  for (let bi = 0; bi < count; bi++) {
    const ba = t * spin + bi * TAU / count;
    const bx = centre.x + Math.cos(ba) * radius * orbit;
    const by = centre.y + Math.sin(ba) * radius * orbit;
    const br = radius * (sizeBase + sizeAmp * Math.sin(t * wobble + bi * wobbleStep));
    const blobGrad = ctx.createRadialGradient(bx, by, 0, bx, by, br);
    blobGrad.addColorStop(0, innerStop);
    blobGrad.addColorStop(1, outerStop);
    ctx.beginPath(); ctx.arc(bx, by, br, 0, TAU);
    ctx.fillStyle = blobGrad; ctx.fill();
  }
}

/**
 * Draw the background nebula for the current folder's compliance score. The
 * colour comes from the score, not the theme, so no theme colours are needed.
 * @param {CanvasRenderingContext2D} ctx
 * @param {{complianceRate: number}|null} curNode - the folder being viewed;
 *   a null node draws nothing.
 * @param {{W: number, H: number, t: number}} frame - the per-frame bundle
 *   renderFrame builds.
 */
export function drawNebula(ctx, curNode, frame) {
  if (!curNode) return;
  const { W, H, t } = frame;
  const nbCol = scoreRGB((curNode.complianceRate || 0) * SCORE_SCALE_MAX);
  const { r: nr, g: ng, b: nb } = nbCol;
  const nbR = Math.max(W, H) * NEBULA.sceneRadiusFraction;
  const nbGrad = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, nbR);
  nbGrad.addColorStop(0, `rgba(${nr},${ng},${nb},${NEBULA.sceneCentreAlpha})`);
  nbGrad.addColorStop(NEBULA.midStopOffset, `rgba(${nr},${ng},${nb},${NEBULA.sceneMidAlpha})`);
  nbGrad.addColorStop(1, `rgba(${nr},${ng},${nb},0)`);
  ctx.beginPath(); ctx.arc(W / 2, H / 2, nbR, 0, TAU);
  ctx.fillStyle = nbGrad; ctx.fill();
  drawNebulaBlobs(
    ctx, { ...NEBULA_SCENE_BLOBS, t }, { x: W / 2, y: H / 2 }, nbR, nbCol, NEBULA.sceneBlobAlpha,
  );
}

/**
 * Draw constellation lines between stars. They share one style, so all
 * segments go into one path and one stroke() per frame.
 */
export function drawConstellationLines(ctx, activeScene, tc, w2s) {
  const { lines, rootStars } = activeScene;
  if (lines.length === 0) return;
  const { r: mr, g: mg, b: mb } = tc.textMuted;
  ctx.beginPath();
  for (const l of lines) {
    const sa = w2s(rootStars[l.a].x, rootStars[l.a].y);
    const sb = w2s(rootStars[l.b].x, rootStars[l.b].y);
    ctx.moveTo(sa.x, sa.y); ctx.lineTo(sb.x, sb.y);
  }
  ctx.strokeStyle = `rgba(${mr},${mg},${mb},0.25)`;
  ctx.lineWidth = 0.8; ctx.stroke();
}

/**
 * Draw a folder star's nebula, texture blobs, and dashed cluster border.
 * Mutates `s.clusterHitR` (the hit-test radius the click handler reads).
 */
function drawFolderNebula(ctx, star, view) {
  const { s, i, sc, sr } = star;
  const { cam, curFly, blobSpec } = view;
  const { r: cr, g: cg, b: cb } = s.col;
  const zoomed = cam.z > FOLDER_NEBULA.zoomedAtZoom;
  const isFlying = curFly && !curFly.reverse && !curFly.swapped && curFly.dimStarIdx === i;
  const nebulaFade = isFlying ? Math.max(0, 1 - (curFly.t / FOLDER_NEBULA.flyFadeOutBy)) : 1;

  const nebulaR = zoomed
    ? (s.radius + FOLDER_NEBULA.zoomedPadPx) * cam.z * FOLDER_NEBULA.zoomedRadiusFraction
    : sr * FOLDER_NEBULA.restRadiusRatio;
  const zoomedAlpha = Math.min(1, (cam.z - FOLDER_NEBULA.zoomedAtZoom) / FOLDER_NEBULA.alphaRampSpan) * FOLDER_NEBULA.zoomedMaxAlpha;
  const nebulaA = (zoomed ? zoomedAlpha : FOLDER_NEBULA.restAlpha) * nebulaFade;
  const nebulaGrad = ctx.createRadialGradient(sc.x, sc.y, 0, sc.x, sc.y, nebulaR);
  nebulaGrad.addColorStop(0, `rgba(${cr},${cg},${cb},${nebulaA})`);
  nebulaGrad.addColorStop(NEBULA.midStopOffset, `rgba(${cr},${cg},${cb},${nebulaA * NEBULA.midAlphaFraction})`);
  nebulaGrad.addColorStop(1, `rgba(${cr},${cg},${cb},0)`);
  ctx.beginPath(); ctx.arc(sc.x, sc.y, nebulaR, 0, TAU);
  ctx.fillStyle = nebulaGrad; ctx.fill();

  // Animated texture blobs
  const zoomedBlobA = Math.min(FOLDER_NEBULA.blobMaxAlpha, (cam.z - FOLDER_NEBULA.zoomedAtZoom) / FOLDER_NEBULA.blobAlphaRampSpan);
  const blobA = (zoomed ? zoomedBlobA : FOLDER_NEBULA.blobRestAlpha) * nebulaFade;
  drawNebulaBlobs(ctx, blobSpec, sc, nebulaR, s.col, blobA);

  // Dashed circle border
  const borderR = sr * FOLDER_NEBULA.borderRadiusRatio;
  ctx.beginPath(); ctx.arc(sc.x, sc.y, borderR, 0, TAU);
  ctx.strokeStyle = `rgba(${cr},${cg},${cb},${FOLDER_NEBULA.borderAlpha * nebulaFade})`;
  ctx.lineWidth = 1;
  ctx.setLineDash(FOLDER_NEBULA_DASH); ctx.stroke(); ctx.setLineDash([]);
  s.clusterHitR = borderR;

  if (!zoomed) {
    ctx.beginPath(); ctx.arc(sc.x, sc.y, sr * FOLDER_NEBULA.innerRingRadiusRatio, 0, TAU);
    ctx.strokeStyle = rgba(s.col, FOLDER_NEBULA.innerRingAlpha); ctx.lineWidth = 0.8; ctx.stroke();
  }
}

/** Draw a star's own violation/alert particles (both folders and files); the
 * severity rings are queued on `cues` and stroked once at the end of the frame. */
function drawFileParticles(ctx, s, sc, cam, t, cues) {
  if (s.particles.length === 0) return;
  const pScale = cam.z * FOLDER_STAR.particleScaleFraction;
  drawParticles(ctx, s.particles, { cx: sc.x, cy: sc.y, scale: pScale, alpha: 0.8, t, drawScale: pScale });
  s.particles.forEach((p) => collectSeverityCue(cues, p, sc, pScale, t));
}

/** Labeled violation orbs around a file star, shown only at high zoom.
 * `view` is the drawStars params bundle: { cam, t, showLabels, ... }. */
function drawLabeledOrbs(ctx, s, sc, view) {
  const { cam, t, showLabels } = view;
  if (s.isFolder || cam.z <= FOLDER_STAR.orbZoomThreshold || s.particles.length === 0) return;
  const vAlpha = Math.min(1, (cam.z - FOLDER_STAR.orbZoomThreshold) / 2);
  const vScale = cam.z * VIOLATION_ORBS.scaleFraction;
  s.particles.forEach(p => {
    const a = t * p.os + p.op;
    const px = sc.x + Math.cos(a) * p.or * p.ec * vScale;
    const py = sc.y + Math.sin(a) * p.or * vScale;
    const tw = VIOLATION_ORBS.twinkleBase + VIOLATION_ORBS.twinkleAmp * Math.sin(t * VIOLATION_ORBS.twinkleSpeed + p.tp);
    const psr = p.sz * vScale * VIOLATION_ORBS.radiusFraction;
    if (psr > FOLDER_STAR.orbMinRadiusPx) {
      drawGlow(ctx, { x: px, y: py, r: psr, col: p.col, alpha: vAlpha * tw });
      if (showLabels && psr > VIOLATION_ORBS.labelMinRadiusPx) {
        const sevName = p.sev.charAt(0).toUpperCase() + p.sev.slice(1);
        const fontPx = Math.max(VIOLATION_ORBS.labelFontMinPx, Math.min(VIOLATION_ORBS.labelFontMaxPx, psr * VIOLATION_ORBS.labelFontRadiusFraction));
        ctx.font = `500 ${fontPx}px ${CANVAS_FONT_FAMILY}`;
        ctx.textAlign = 'center'; ctx.fillStyle = rgba(p.col, VIOLATION_ORBS.labelAlpha * vAlpha);
        ctx.fillText(sevName, px, py - psr - VIOLATION_ORBS.labelOffsetPx);
      }
    }
  });
}

/** Collect this star's label-placement info (or null), for the collision pass in drawLabels. */
function collectStarLabel(s, sc, sr, cam, showLabels) {
  if (!showLabels || sr <= 1) return null;
  const fs = Math.min(cam.z, FOLDER_LABEL.scaleCap);
  const shortName = s.name.includes('/') ? s.name.split('/')[0] : s.name;
  const label = s.isFolder ? shortName : s.name;
  const fontSize = Math.max(FOLDER_LABEL.fontMinPx, FOLDER_LABEL.fontPx * fs);
  const lw = label.length * fontSize * FOLDER_LABEL.charWidthFraction;
  const lh = fontSize + FOLDER_LABEL.heightPadPx;
  const lx = sc.x;
  const ly = sc.y - sr - FOLDER_LABEL.offsetPx * fs;
  const importance = (s.isFolder ? 1000 : 0) + (s.violations || 0) + (s.radius || 0);
  return { s, sc, sr, fs, label, fontSize, lx, ly, lw, lh, importance, col: s.col };
}

/** Hit-test this star against the mouse position (idle only — no anim/fly in progress). */
function hitTestStar({ s, i, sc, sr }, params) {
  const { animRef, mouseRef, flyRef } = params;
  const fly = flyRef.current;
  const mx = mouseRef.current.x, my = mouseRef.current.y;
  if (animRef.current || fly || mx < 0) return null;
  const dx = mx - sc.x, dy = my - sc.y;
  const d2 = dx * dx + dy * dy;
  const clusterR = s.isFolder && s.clusterHitR > 0 ? s.clusterHitR : 0;
  const starHitR = Math.max(sr * 2, FOLDER_STAR.hitRadiusMinPx);
  if (d2 < starHitR * starHitR || (clusterR > 0 && d2 < clusterR * clusterR)) {
    return { type: s.isFolder ? HIT_TARGET_TYPE.FOLDER : HIT_TARGET_TYPE.FILE, starIdx: i, data: s };
  }
  return null;
}

/**
 * Draw all stars and collect label/hit-test info. Returns { pendingLabels, newHovered }.
 */
export function drawStars(ctx, activeScene, params) {
  const { t, cam, w2s, showLabels, flyRef } = params;
  let newHovered = null;
  const pendingLabels = [];
  const cues = newCueBatch();
  // Built once per frame, not once per folder star.
  const blobSpec = { ...NEBULA_FOLDER_BLOBS, t };

  activeScene.rootStars.forEach((s, i) => {
    const sc = w2s(s.x, s.y);
    const pulse = 1 + STAR.pulseAmplitude * Math.sin(t * STAR.pulseSpeed + s.pp);
    const sr = s.radius * pulse * cam.z * STAR.screenRadiusFraction;

    const curFly = flyRef.current;
    const dimThreshold = FOLDER_STAR.dimAboveRadiusPx;
    const starAlpha = s.isFolder && sr > dimThreshold
      ? Math.max(FOLDER_STAR.dimMinAlpha, 1 - (sr - dimThreshold) / FOLDER_STAR.dimFadeSpanPx)
      : 1;
    drawGlow(ctx, { x: sc.x, y: sc.y, r: sr, col: s.col, alpha: starAlpha });

    if (s.isFolder) drawFolderNebula(ctx, { s, i, sc, sr }, { cam, curFly, blobSpec });
    drawFileParticles(ctx, s, sc, cam, t, cues);
    drawLabeledOrbs(ctx, s, sc, params);

    const label = collectStarLabel(s, sc, sr, cam, showLabels);
    if (label) pendingLabels.push(label);

    const hovered = hitTestStar({ s, i, sc, sr }, params);
    if (hovered) newHovered = hovered;
  });

  drawCueBatch(ctx, cues);
  return { pendingLabels, newHovered };
}

/**
 * Draw labels with collision avoidance.
 */
export function drawLabels(ctx, pendingLabels, tc) {
  pendingLabels.sort((a, b) => b.importance - a.importance);
  const placedLabels = [];
  pendingLabels.forEach(lb => {
    const halfW = lb.lw / 2, halfH = lb.lh / 2;
    const collides = placedLabels.some(pl => {
      return Math.abs(lb.lx - pl.lx) < (halfW + pl.lw / 2 + FOLDER_LABEL.collisionPadXPx) &&
             Math.abs(lb.ly - pl.ly) < (halfH + pl.lh / 2 + 2);
    });
    if (collides) return;
    placedLabels.push(lb);
    ctx.font = `500 ${lb.fontSize}px ${CANVAS_FONT_FAMILY}`;
    ctx.textAlign = 'center';
    ctx.fillStyle = rgba(tc.text, LABEL_ALPHA);
    ctx.fillText(lb.label, lb.lx, lb.ly);
    // The font string stays inside each branch: a file star with no
    // violations draws no sub-line at all, and building it up here would
    // cost that star a string per frame for nothing.
    const subSize = Math.max(FOLDER_LABEL.subFontMinPx, FOLDER_LABEL.subFontPx * lb.fs);
    const subDrop = FOLDER_LABEL.subOffsetPx * lb.fs;
    if (lb.s.violations > 0) {
      ctx.font = `${subSize}px ${CANVAS_FONT_FAMILY}`;
      ctx.fillStyle = rgba(tc.textMuted, FOLDER_LABEL.subLineAlpha);
      ctx.fillText(lb.s.violations + ' viol.', lb.sc.x, lb.sc.y + lb.sr + subDrop);
    } else if (lb.s.isFolder) {
      ctx.font = `${subSize}px ${CANVAS_FONT_FAMILY}`;
      ctx.fillStyle = rgba(tc.textMuted, FOLDER_LABEL.rateAlpha);
      ctx.fillText((lb.s.complianceRate * PERCENT).toFixed(0) + '%', lb.sc.x, lb.sc.y + lb.sr + subDrop);
    }
  });
}
