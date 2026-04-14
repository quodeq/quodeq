import {
  TAU, getThemeColors, scoreRGB, rgba,
  drawGlow, drawParticles,
} from '../core/galaxyCore.js';

/**
 * Draw all scene elements to the canvas context.
 */
export function drawScene(ctx, activeScene, params) {
  const { W, H, t, cam, w2s, showLabels, mouseRef, flyRef, focusedFolderRef, canvasRef } = params;
  const tc = getThemeColors(canvasRef.current?.parentElement);

  // Background gradient
  const grad = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, Math.max(W, H) * 0.6);
  grad.addColorStop(0, tc.bgAlt); grad.addColorStop(1, tc.bg);
  ctx.fillStyle = grad; ctx.fillRect(0, 0, W, H);

  return { tc };
}

/**
 * Draw background nebula for the current folder's compliance score.
 */
export function drawNebula(ctx, curNode, tc, W, H, t) {
  if (!curNode) return;
  const nbCol = scoreRGB((curNode.complianceRate || 0) * 10);
  const { r: nr, g: ng, b: nb } = nbCol;
  const nbR = Math.max(W, H) * 0.7;
  const nbGrad = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, nbR);
  nbGrad.addColorStop(0, `rgba(${nr},${ng},${nb},0.015)`);
  nbGrad.addColorStop(0.5, `rgba(${nr},${ng},${nb},0.007)`);
  nbGrad.addColorStop(1, `rgba(${nr},${ng},${nb},0)`);
  ctx.beginPath(); ctx.arc(W / 2, H / 2, nbR, 0, TAU);
  ctx.fillStyle = nbGrad; ctx.fill();
  for (let bi = 0; bi < 4; bi++) {
    const ba = t * 0.005 + bi * TAU / 4;
    const bx = W / 2 + Math.cos(ba) * nbR * 0.35;
    const by = H / 2 + Math.sin(ba) * nbR * 0.35;
    const br = nbR * (0.3 + 0.08 * Math.sin(t * 0.015 + bi * 1.7));
    const blGrad = ctx.createRadialGradient(bx, by, 0, bx, by, br);
    blGrad.addColorStop(0, `rgba(${nr},${ng},${nb},0.008)`);
    blGrad.addColorStop(1, `rgba(${nr},${ng},${nb},0)`);
    ctx.beginPath(); ctx.arc(bx, by, br, 0, TAU);
    ctx.fillStyle = blGrad; ctx.fill();
  }
}

/**
 * Draw background starfield.
 */
export function drawStarfield(ctx, bg, tc, W, H, t) {
  const { r: mr, g: mg, b: mb } = tc.textMuted;
  bg.forEach(s => {
    const a = 0.15 + 0.15 * Math.sin(t * s.sp + s.tw);
    ctx.beginPath(); ctx.arc(s.x * W, s.y * H, s.sz, 0, TAU);
    ctx.fillStyle = `rgba(${mr},${mg},${mb},${a})`; ctx.fill();
  });
}

/**
 * Draw constellation lines between stars.
 */
export function drawConstellationLines(ctx, activeScene, tc, w2s) {
  const { r: mr, g: mg, b: mb } = tc.textMuted;
  activeScene.lines.forEach(l => {
    const sa = w2s(activeScene.rootStars[l.a].x, activeScene.rootStars[l.a].y);
    const sb = w2s(activeScene.rootStars[l.b].x, activeScene.rootStars[l.b].y);
    ctx.beginPath(); ctx.moveTo(sa.x, sa.y); ctx.lineTo(sb.x, sb.y);
    ctx.strokeStyle = `rgba(${mr},${mg},${mb},0.25)`;
    ctx.lineWidth = 0.8; ctx.stroke();
  });
}

/**
 * Draw all stars and collect label/hit-test info. Returns { pendingLabels, newHovered }.
 */
export function drawStars(ctx, activeScene, params) {
  const { t, cam, w2s, showLabels, mouseRef, flyRef, focusedFolderRef, animRef, tc } = params;
  const mx = mouseRef.current.x, my = mouseRef.current.y;
  let newHovered = null;
  const pendingLabels = [];
  const fly = flyRef.current;

  activeScene.rootStars.forEach((s, i) => {
    const sc = w2s(s.x, s.y);
    const pulse = 1 + 0.01 * Math.sin(t * 0.4 + s.pp);
    const sr = s.radius * pulse * cam.z * 0.5;

    const curFly = flyRef.current;
    const isFocusedFolder = s.isFolder && (
      (focusedFolderRef.current && focusedFolderRef.current.starIdx === i) ||
      (curFly && !curFly.reverse && !curFly.swapped && curFly.dimStarIdx === i)
    );
    const dimThreshold = 30;
    const starAlpha = s.isFolder && sr > dimThreshold
      ? Math.max(0.15, 1 - (sr - dimThreshold) / 80)
      : 1;
    drawGlow(ctx, { x: sc.x, y: sc.y, r: sr, col: s.col, alpha: starAlpha });

    // Folder stars: nebula + cluster detail
    if (s.isFolder) {
      const { r: cr, g: cg, b: cb } = s.col;
      const zoomed = cam.z > 2;
      const isFlying = curFly && !curFly.reverse && !curFly.swapped && curFly.dimStarIdx === i;
      const nebulaFade = isFlying ? Math.max(0, 1 - (curFly.t / 0.35)) : 1;

      const nebulaR = zoomed
        ? (s.radius + 40) * cam.z * 0.4
        : sr * 5;
      const nebulaA = (zoomed ? Math.min(1, (cam.z - 2) / 3) * 0.35 : 0.08) * nebulaFade;
      const nebulaGrad = ctx.createRadialGradient(sc.x, sc.y, 0, sc.x, sc.y, nebulaR);
      nebulaGrad.addColorStop(0, `rgba(${cr},${cg},${cb},${nebulaA})`);
      nebulaGrad.addColorStop(0.5, `rgba(${cr},${cg},${cb},${nebulaA * 0.5})`);
      nebulaGrad.addColorStop(1, `rgba(${cr},${cg},${cb},0)`);
      ctx.beginPath(); ctx.arc(sc.x, sc.y, nebulaR, 0, TAU);
      ctx.fillStyle = nebulaGrad; ctx.fill();

      // Animated texture blobs
      const blobA = (zoomed ? Math.min(0.18, (cam.z - 2) / 15) : 0.025) * nebulaFade;
      for (let bi = 0; bi < 3; bi++) {
        const ba = t * 0.01 + bi * TAU / 3;
        const bx = sc.x + Math.cos(ba) * nebulaR * 0.3;
        const by = sc.y + Math.sin(ba) * nebulaR * 0.3;
        const br = nebulaR * (0.4 + 0.1 * Math.sin(t * 0.02 + bi * 2));
        const blobGrad = ctx.createRadialGradient(bx, by, 0, bx, by, br);
        blobGrad.addColorStop(0, `rgba(${cr},${cg},${cb},${blobA})`);
        blobGrad.addColorStop(1, `rgba(${cr},${cg},${cb},0)`);
        ctx.beginPath(); ctx.arc(bx, by, br, 0, TAU);
        ctx.fillStyle = blobGrad; ctx.fill();
      }

      // Dashed circle border
      const borderR = sr * 3.5;
      ctx.beginPath(); ctx.arc(sc.x, sc.y, borderR, 0, TAU);
      ctx.strokeStyle = `rgba(${cr},${cg},${cb},${0.1 * nebulaFade})`;
      ctx.lineWidth = 1;
      ctx.setLineDash([6, 12]); ctx.stroke(); ctx.setLineDash([]);
      s._clusterHitR = borderR;

      if (!zoomed) {
        ctx.beginPath(); ctx.arc(sc.x, sc.y, sr * 2.2, 0, TAU);
        ctx.strokeStyle = rgba(s.col, 0.12); ctx.lineWidth = 0.8; ctx.stroke();
      }
    }

    // File particles
    if (s.particles.length > 0) {
      const pScale = cam.z * 0.5;
      drawParticles(ctx, s.particles, { cx: sc.x, cy: sc.y, scale: pScale, alpha: 0.8, t, drawScale: pScale });
    }

    // Labeled violation orbs at high zoom
    if (!s.isFolder && cam.z > 2.5 && s.particles.length > 0) {
      const vAlpha = Math.min(1, (cam.z - 2.5) / 2);
      const vScale = cam.z * 0.06;
      s.particles.forEach(p => {
        const a = t * p.os + p.op;
        const px = sc.x + Math.cos(a) * p.or * p.ec * vScale;
        const py = sc.y + Math.sin(a) * p.or * vScale;
        const tw = 0.5 + 0.06 * Math.sin(t * 0.4 + p.tp);
        const psr = p.sz * vScale * 0.5;
        if (psr > 1.5) {
          drawGlow(ctx, { x: px, y: py, r: psr, col: p.col, alpha: vAlpha * tw });
          if (showLabels && psr > 3) {
            const sevName = p.sev.charAt(0).toUpperCase() + p.sev.slice(1);
            ctx.font = `500 ${Math.max(7, Math.min(11, psr * 0.8))}px -apple-system,BlinkMacSystemFont,sans-serif`;
            ctx.textAlign = 'center'; ctx.fillStyle = rgba(p.col, 0.85 * vAlpha);
            ctx.fillText(sevName, px, py - psr - 4);
          }
        }
      });
    }

    // Collect label info
    if (showLabels && sr > 1) {
      const fs = Math.min(cam.z, 1.5);
      const shortName = s.name.includes('/') ? s.name.split('/')[0] : s.name;
      const label = s.isFolder ? shortName : s.name;
      const fontSize = Math.max(9, 11 * fs);
      const lw = label.length * fontSize * 0.55;
      const lh = fontSize + 4;
      const lx = sc.x;
      const ly = sc.y - sr - 14 * fs;
      const importance = (s.isFolder ? 1000 : 0) + (s.violations || 0) + (s.radius || 0);
      pendingLabels.push({ s, sc, sr, fs, label, fontSize, lx, ly, lw, lh, importance, col: s.col });
    }

    // Hit testing
    if (!animRef.current && !fly && mx >= 0) {
      const dx = mx - sc.x, dy = my - sc.y;
      const d2 = dx * dx + dy * dy;
      const clusterR = s.isFolder && s._clusterHitR > 0 ? s._clusterHitR : 0;
      const starHitR = Math.max(sr * 2, 14);
      if (d2 < starHitR * starHitR || (clusterR > 0 && d2 < clusterR * clusterR)) {
        newHovered = { type: s.isFolder ? 'folder' : 'file', starIdx: i, data: s };
      }
    }
  });

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
      return Math.abs(lb.lx - pl.lx) < (halfW + pl.lw / 2 + 4) &&
             Math.abs(lb.ly - pl.ly) < (halfH + pl.lh / 2 + 2);
    });
    if (collides) return;
    placedLabels.push(lb);
    ctx.font = `500 ${lb.fontSize}px -apple-system,BlinkMacSystemFont,sans-serif`;
    ctx.textAlign = 'center';
    ctx.fillStyle = rgba(tc.text, 0.6);
    ctx.fillText(lb.label, lb.lx, lb.ly);
    if (lb.s.violations > 0) {
      ctx.font = `${Math.max(7, 9 * lb.fs)}px -apple-system,BlinkMacSystemFont,sans-serif`;
      ctx.fillStyle = rgba(tc.textMuted, 0.6);
      ctx.fillText(lb.s.violations + ' viol.', lb.sc.x, lb.sc.y + lb.sr + 12 * lb.fs);
    } else if (lb.s.isFolder) {
      ctx.font = `${Math.max(7, 9 * lb.fs)}px -apple-system,BlinkMacSystemFont,sans-serif`;
      ctx.fillStyle = rgba(tc.textMuted, 0.5);
      ctx.fillText((lb.s.complianceRate * 100).toFixed(0) + '%', lb.sc.x, lb.sc.y + lb.sr + 12 * lb.fs);
    }
  });
}
