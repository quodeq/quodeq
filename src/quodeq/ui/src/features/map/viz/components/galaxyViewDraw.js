import {
  TAU, getThemeColors, drawGlow, drawParticles, rgba, rgb,
} from '../core/galaxyCore.js';

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
  const { W, H, t, mx, my, showLabels, animating, rDim, rPrin, w2s, parentEl } = opts;

  // --- Background ---
  const tc = getThemeColors(parentEl);
  const grad = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, Math.max(W, H) * 0.6);
  grad.addColorStop(0, tc.bgAlt); grad.addColorStop(1, tc.bg);
  ctx.fillStyle = grad; ctx.fillRect(0, 0, W, H);
  const { r: mr, g: mg, b: mb } = tc.textMuted;
  scene.bg.forEach(s => {
    const a = 0.15 + 0.15 * Math.sin(t * s.sp + s.tw);
    ctx.beginPath(); ctx.arc(s.x * W, s.y * H, s.sz, 0, TAU);
    ctx.fillStyle = `rgba(${mr},${mg},${mb},${a})`; ctx.fill();
  });

  // --- Constellation lines and labels (only at galaxy level) ---
  if (cam.z < 3) {
    const conAlpha = Math.max(0, 1 - (cam.z - 1) / 2);
    (scene.constellations || []).forEach(con => {
      const isFocused = nav.clusterCx == null || (con.cx === nav.clusterCx && con.cy === nav.clusterCy);
      const conClusterDim = isFocused ? 1 : Math.max(0.08, 1 - (cam.z - 1) / 2);
      // Dashed circle around cluster
      const csc = w2s(W / 2 + con.cx, H / 2 + con.cy);
      const circleR = (con.spread + 10) * cam.z;
      ctx.beginPath(); ctx.arc(csc.x, csc.y, circleR, 0, TAU);
      ctx.strokeStyle = `rgba(${mr},${mg},${mb},${0.15 * conAlpha * conClusterDim})`;
      ctx.lineWidth = 1;
      ctx.setLineDash([8, 14]); ctx.stroke(); ctx.setLineDash([]);

      // Constellation lines between stars
      con.lines.forEach(l => {
        const sa = w2s(scene.stars[l.a].x, scene.stars[l.a].y);
        const sb = w2s(scene.stars[l.b].x, scene.stars[l.b].y);
        ctx.beginPath(); ctx.moveTo(sa.x, sa.y); ctx.lineTo(sb.x, sb.y);
        ctx.strokeStyle = `rgba(${mr},${mg},${mb},${0.4 * conAlpha * conClusterDim})`;
        ctx.lineWidth = 0.8;
        ctx.setLineDash([3, 5]); ctx.stroke(); ctx.setLineDash([]);
      });
      // Constellation label — above the dashed circle
      if (showLabels && con.label) {
        const lx = csc.x;
        const ly = csc.y - circleR - 10;
        ctx.font = '600 14px -apple-system,BlinkMacSystemFont,sans-serif';
        ctx.textAlign = 'center';
        ctx.fillStyle = `rgba(${mr},${mg},${mb},${0.55 * conAlpha * conClusterDim})`;
        ctx.fillText(con.label, lx, ly);
        con._lx = lx; con._ly = ly;
      }
    });
  }

  // --- Dimension stars + principle particles orbiting them ---
  let newHovered = null;
  scene.stars.forEach((s, i) => {
    const sc = w2s(s.x, s.y);
    const pulse = 1 + 0.01 * Math.sin(t * 0.4 + s.pp);
    const isSelected = rDim === i;
    const sr = s.radius * pulse * cam.z * 0.5;
    // Dim stars not in the focused cluster
    const inFocusedCluster = nav.clusterCx == null || (s._clusterCx === nav.clusterCx && s._clusterCy === nav.clusterCy);
    const clusterDim = inFocusedCluster ? 1 : Math.max(0.08, 1 - (cam.z - 1) / 2);
    // All dim-level decorations fade out once we zoom past galaxy level
    const dimFade = isSelected ? 1 : Math.max(0, 1 - (cam.z - 1.5) / 3) * clusterDim;

    // Principle particles orbiting this dimension — fade out as principle planets fade in
    const particleAlpha = isSelected ? Math.max(0, 1 - (cam.z - 1.5) / 2) : dimFade;
    if (particleAlpha > 0.01) {
      (scene.principles[i] || []).forEach(p => {
        const dp = p.dimParticle;
        const a = t * dp.os + dp.op;
        const px = sc.x + Math.cos(a) * dp.or * dp.ec * cam.z;
        const py = sc.y + Math.sin(a) * dp.or * cam.z;
        const tw = 0.5 + 0.08 * Math.sin(t * 0.6 + dp.tp);
        const sz = dp.sz * cam.z;
        if (sz > 0.3) {
          const { r, g, b } = dp.col;
          ctx.beginPath(); ctx.arc(px, py, sz * 2.5, 0, TAU);
          ctx.fillStyle = `rgba(${r},${g},${b},${tw * 0.08 * particleAlpha})`; ctx.fill();
          ctx.beginPath(); ctx.arc(px, py, sz, 0, TAU);
          ctx.fillStyle = `rgba(${r},${g},${b},${(tw + 0.15) * particleAlpha})`; ctx.fill();
        }
      });
    }

    drawGlow(ctx, sc.x, sc.y, sr, s.col, isSelected ? clusterDim : dimFade);
    // Hide dimension label when zoomed past galaxy level
    const labelAlpha = isSelected ? Math.max(0, 1 - (cam.z - 1.5) / 2) : dimFade;
    if (showLabels && labelAlpha > 0.01) {
      const fs = Math.min(cam.z, 1.5);
      ctx.font = `600 ${Math.max(11, 14 * fs)}px -apple-system,BlinkMacSystemFont,sans-serif`;
      ctx.textAlign = 'center'; ctx.fillStyle = rgba(tc.text, 0.6 * labelAlpha);
      ctx.fillText(s.name, sc.x, sc.y - sr - 24 * fs);
      ctx.font = `${Math.max(9, 12 * fs)}px -apple-system,BlinkMacSystemFont,sans-serif`;
      ctx.fillStyle = rgba(tc.textMuted, 0.8 * labelAlpha);
      ctx.fillText(s.score.toFixed(1), sc.x, sc.y + sr + 24 * fs);
    }
    if (!animating && nav.depth === 0 && mx >= 0) {
      const dx = mx - sc.x, dy = my - sc.y;
      const hitR = Math.max(sr * 2, 20);
      if (dx * dx + dy * dy < hitR * hitR) newHovered = { type: 'dim', idx: i, data: s };
    }
  });

  // --- Principles as planets (visible when zoomed into a dimension) ---
  if (cam.z > 1.5 && rDim !== null) {
    const dim = scene.stars[rDim];
    const dsc = w2s(dim.x, dim.y);
    const pAlpha = Math.min(1, (cam.z - 1.5) / 3);
    const pScale = cam.z * 0.12;
    (scene.principles[rDim] || []).forEach((p, pi) => {
      const isSelectedPrin = nav.prin === pi;
      const sc = w2s(p.x, p.y);
      const sr = p.radius * pScale;
      // orbit ring
      ctx.beginPath(); ctx.arc(dsc.x, dsc.y, Math.hypot(sc.x - dsc.x, sc.y - dsc.y), 0, TAU);
      ctx.strokeStyle = `rgba(50,55,80,${0.1 * pAlpha})`; ctx.lineWidth = 0.5; ctx.stroke();
      // connection line
      ctx.beginPath(); ctx.moveTo(dsc.x, dsc.y); ctx.lineTo(sc.x, sc.y);
      ctx.strokeStyle = rgba(dim.col, 0.04 * pAlpha); ctx.lineWidth = 0.8; ctx.stroke();
      // Violation/compliance particles — fade out on selected (large orbs take over), shrink on others
      const particleFade = isSelectedPrin ? Math.max(0, 1 - (cam.z - 12) / 20) : 1;
      // Non-selected: smaller particles but keep orbit wide so they don't collide with planet
      const cappedScale = Math.min(0.8, 5 * 0.12 / Math.max(pScale, 0.01));
      const particleDrawScale = isSelectedPrin ? pScale * 0.8 : pScale * cappedScale;
      const particleOrbitScale = isSelectedPrin ? pScale * 0.8 : pScale * Math.max(cappedScale, 0.5);
      if (particleFade > 0.01) drawParticles(ctx, sc.x, sc.y, p.particles, particleOrbitScale, pAlpha * particleFade, t, particleDrawScale);
      drawGlow(ctx, sc.x, sc.y, sr, p.col, pAlpha);
      // Only fade labels/scores — hide on non-selected when zoomed into a principle
      const prinLabelAlpha = isSelectedPrin ? Math.max(0, 1 - (cam.z - 12) / 20) : (nav.prin !== null ? Math.max(0, 1 - (cam.z - 12) / 15) : 1);
      if (showLabels && prinLabelAlpha > 0.01) {
        const la = pAlpha * prinLabelAlpha;
        ctx.font = `600 14px -apple-system,BlinkMacSystemFont,sans-serif`;
        ctx.textAlign = 'center'; ctx.fillStyle = rgba(tc.text, 0.6 * la);
        ctx.fillText(p.name, sc.x, sc.y - sr - 10);
        ctx.font = `12px -apple-system,BlinkMacSystemFont,sans-serif`;
        ctx.fillStyle = rgba(tc.textMuted, 0.7 * la);
        ctx.fillText(p.score.toFixed(1), sc.x, sc.y + sr + 16);
      }
      if (!animating && nav.depth === 1 && pAlpha > 0.4 && mx >= 0) {
        const dx = mx - sc.x, dy = my - sc.y;
        if (dx * dx + dy * dy < (sr + 10) * (sr + 10)) newHovered = { type: 'prin', idx: pi, data: p };
      }
    });
  }

  // --- Zoomed into principle — violation/compliance particles as large orbs ---
  if (cam.z > 12 && rDim !== null && rPrin !== null) {
    const prin = scene.principles[rDim][rPrin];
    const psc = w2s(prin.x, prin.y);
    const vAlpha = Math.min(1, (cam.z - 12) / 20);
    const vScale = cam.z * 0.06;
    prin.particles.forEach((p) => {
      const a = t * p.os + p.op;
      const px = psc.x + Math.cos(a) * p.or * p.ec * vScale;
      const py = psc.y + Math.sin(a) * p.or * vScale;
      const tw = 0.5 + 0.06 * Math.sin(t * 0.4 + p.tp);
      const sr = p.sz * vScale * 0.5;
      drawGlow(ctx, px, py, sr, p.col, vAlpha * tw);
      if (showLabels && sr > 3) {
        const sevName = p.sev.charAt(0).toUpperCase() + p.sev.slice(1);
        ctx.font = `500 ${Math.max(7, Math.min(11, sr * 0.8))}px -apple-system,BlinkMacSystemFont,sans-serif`;
        ctx.textAlign = 'center'; ctx.fillStyle = rgba(p.col, 0.85 * vAlpha);
        ctx.fillText(sevName, px, py - sr - 4);
      }
    });
  }

  return { hovered: newHovered };
}
