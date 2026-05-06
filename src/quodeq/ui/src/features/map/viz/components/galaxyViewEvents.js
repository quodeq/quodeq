import { rgb } from '../core/galaxyCore.js';
import { escapeHtml } from '../../../../utils/escapeHtml.js';

/**
 * Build tooltip HTML and position it.
 *
 * @param {HTMLElement} el - The tooltip DOM element
 * @param {object|null} hovered - Current hovered item { type, idx, data }
 * @param {boolean} animating - Whether a camera transition is active
 * @param {number} cx - Client X position
 * @param {number} cy - Client Y position
 */
export function updateTooltip(el, hovered, animating, cx, cy) {
  if (!el) return;
  if (!hovered || animating) { el.style.display = 'none'; return; }
  const d = hovered.data;
  // label/value are escaped so this helper stays safe even if a future
  // caller passes a string from data instead of the current numeric/literal
  // values. Color is hardcoded by callers (CSS var or rgb()) so it bypasses
  // escape — but is still wrapped in a fixed style attribute.
  const row = (label, value, color) =>
    `<div style="display:flex;justify-content:space-between;gap:12px;color:${color || 'var(--color-text-muted)'}"><span>${escapeHtml(String(label))}</span><span style="color:${color || 'var(--color-text)'};font-weight:500">${escapeHtml(String(value))}</span></div>`;
  const rows = [row('Score', d.score.toFixed(1))];
  if (hovered.type === 'dim') rows.push(row('Principles', d.principleCount));
  rows.push(row('Violations', d.violations));
  if (d.violations > 0) {
    // For dimensions: compute severity from raw violations; for principles: use stored counts
    let sc = d.critical, sm = d.major, sn = d.minor;
    if (sc == null && d._raw?.violations) {
      sc = sm = sn = 0;
      (d._raw.violations || []).forEach(v => {
        const s = v.severity || 'minor';
        if (s === 'critical') sc++;
        else if (s === 'major') sm++;
        else sn++;
      });
    }
    if (sc > 0) rows.push(row('Critical', sc, 'var(--color-sev-critical-text)'));
    if (sm > 0) rows.push(row('Major', sm, 'var(--color-sev-major-text)'));
    if (sn > 0) rows.push(row('Minor', sn, 'var(--color-sev-minor-text)'));
  }
  rows.push(row('Compliance', d.compliance));
  el.innerHTML = `<div style="font-weight:600;color:${rgb(d.col)};margin-bottom:4px">${escapeHtml(d.name)}</div>
    ${rows.join('')}
    <div style="margin-top:6px;color:var(--color-text-muted);font-size:11px;opacity:0.6">Click to explore</div>`;
  el.style.display = 'block';
  el.style.left = Math.min(cx + 16, window.innerWidth - 200) + 'px';
  el.style.top = Math.min(cy + 16, window.innerHeight - 160) + 'px';
}

/**
 * Handle click on the galaxy canvas — navigate into stars/principles or zoom to clusters.
 *
 * @param {MouseEvent} e
 * @param {object} refs - { hoveredRef, navRef, animRef, camRef, canvasRef }
 * @param {object} scene - The scene data
 * @param {object} size - { w, h }
 * @param {Function} navigateTo - (depth, dim, prin) => void
 * @param {Function} startTransition - (zoomingOut) => void
 * @param {Function} saveNav - () => void
 * @param {Function} w2s - World-to-screen transform
 */
export function handleCanvasClick(e, refs, scene, size, navigateTo, startTransition, saveNav, w2s) {
  const { hoveredRef, navRef, animRef, camRef, canvasRef } = refs;
  const h = hoveredRef.current;
  const nav = navRef.current;

  if (h) {
    if (nav.depth === 0 && h.type === 'dim') navigateTo(1, h.idx);
    else if (nav.depth === 1 && h.type === 'prin') navigateTo(2, nav.dim, h.idx);
    return;
  }

  // At galaxy root: check if click is near a cluster -> zoom to it
  if (nav.depth === 0 && !animRef.current && scene?.constellations) {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (rect) {
      const cmx = e.clientX - rect.left, cmy = e.clientY - rect.top;
      for (const con of scene.constellations) {
        const csc = w2s(size.w / 2 + con.cx, size.h / 2 + con.cy);
        const dx = cmx - csc.x, dy = cmy - csc.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        const hitRadius = (con.spread + 40) * camRef.current.z;
        if (dist < hitRadius) {
          if (nav.clusterCx === con.cx && nav.clusterCy === con.cy) {
            // Already in this cluster — zoom back to galaxy
            nav.clusterCx = null; nav.clusterCy = null;
            startTransition(true);
          } else {
            // Zoom to this cluster
            nav.clusterCx = con.cx; nav.clusterCy = con.cy;
            startTransition(false);
          }
          saveNav();
          return;
        }
      }
    }
  }

  // Click empty space (outside any cluster)
  if (nav.depth > 0) {
    if (nav.depth === 2) navigateTo(1, nav.dim);
    else navigateTo(0);
  } else if (nav.clusterCx != null) {
    // Zoomed into cluster but clicked far from it — zoom back
    nav.clusterCx = null; nav.clusterCy = null;
    startTransition(true);
    saveNav();
  }
}
