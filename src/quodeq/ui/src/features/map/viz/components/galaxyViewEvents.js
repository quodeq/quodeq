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
    if (!camRef.current) return;
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

/**
 * The nodes a keyboard user can move focus across at the current depth.
 * Depth 0 → dimension stars; depth 1 → the active dimension's principles;
 * depth 2 (zoomed into a single principle) has no siblings to traverse.
 *
 * @param {object|null} scene - The scene data
 * @param {object} nav - Navigation state { depth, dim, prin }
 * @returns {Array} focusable node objects (may be empty)
 */
export function focusableNodes(scene, nav) {
  if (!scene) return [];
  if (nav.depth === 0) return scene.stars ?? [];
  if (nav.depth === 1 && nav.dim !== null && nav.dim !== undefined) {
    return scene.principles?.[nav.dim] ?? [];
  }
  return [];
}

function announceNode(announce, node, idx, total) {
  if (!announce || !node) return;
  const score = typeof node.score === 'number' ? `, score ${node.score.toFixed(1)}` : '';
  announce(`${node.name}${score}, ${idx + 1} of ${total}`);
}

/**
 * Build keyboard handlers for the galaxy canvas (a11y, #675).
 *
 * The canvas has no per-node DOM, so focus is tracked as an index into the
 * current depth's node list (`focusedIdxRef`) and the renderer draws a ring
 * on it. Arrow keys move focus across siblings; Enter/Space drills in via the
 * same `navigateTo` the mouse click uses; Escape steps back up. Movements are
 * announced through an aria-live region so screen-reader users get feedback.
 *
 * @param {object} refs - { navRef, animRef, focusedIdxRef }
 * @param {object} params - { scene, navigateTo, startTransition, saveNav, announce }
 * @returns {{ handleKeyDown: Function, handleFocus: Function, handleBlur: Function }}
 */
export function createKeyboardHandlers(refs, params) {
  const { navRef, animRef, focusedIdxRef } = refs;
  const { scene, navigateTo, startTransition, saveNav, announce } = params;

  function focusAt(idx) {
    const nodes = focusableNodes(scene, navRef.current);
    if (!nodes.length) return;
    const clamped = ((idx % nodes.length) + nodes.length) % nodes.length;
    focusedIdxRef.current = clamped;
    announceNode(announce, nodes[clamped], clamped, nodes.length);
  }

  function move(delta) {
    const nodes = focusableNodes(scene, navRef.current);
    if (!nodes.length) return;
    const cur = focusedIdxRef.current;
    focusAt(cur === null ? (delta > 0 ? 0 : nodes.length - 1) : cur + delta);
  }

  function activate() {
    const nav = navRef.current;
    const nodes = focusableNodes(scene, nav);
    const idx = focusedIdxRef.current;
    if (idx === null || !nodes[idx]) return;
    const node = nodes[idx];
    if (nav.depth === 0) navigateTo(1, idx);
    else if (nav.depth === 1) navigateTo(2, nav.dim, idx);
    else return;
    focusedIdxRef.current = null;
    if (announce) announce(`Opened ${node.name}`);
  }

  function goUp() {
    const nav = navRef.current;
    if (nav.depth === 2) { navigateTo(1, nav.dim); announce?.('Returned to principles'); }
    else if (nav.depth === 1) { navigateTo(0); announce?.('Returned to galaxy overview'); }
    else if (nav.clusterCx != null) {
      nav.clusterCx = null; nav.clusterCy = null;
      startTransition(true); saveNav();
      announce?.('Returned to galaxy overview');
    } else return false;
    focusedIdxRef.current = null;
    return true;
  }

  function handleKeyDown(e) {
    if (animRef.current) return; // mid-transition: let the camera settle first
    switch (e.key) {
      case 'ArrowRight':
      case 'ArrowDown':
        e.preventDefault(); move(1); break;
      case 'ArrowLeft':
      case 'ArrowUp':
        e.preventDefault(); move(-1); break;
      case 'Enter':
      case ' ':
        e.preventDefault(); activate(); break;
      case 'Escape':
        if (goUp() !== false) e.preventDefault();
        break;
      default: break;
    }
  }

  function handleFocus() {
    if (focusedIdxRef.current === null) focusAt(0);
  }

  function handleBlur() {
    focusedIdxRef.current = null;
  }

  return { handleKeyDown, handleFocus, handleBlur };
}
