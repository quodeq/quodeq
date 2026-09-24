import { rgb } from '../core/galaxyCore.js';
import { GALAXY_VIEW_HOVER_TYPE } from '../core/galaxyHitTypes.js';
import { pushSeverityRows, showTooltip } from './galaxyTooltipDom.js';
import { escapeHtml } from '../../../../utils/escapeHtml.js';
import { t } from '../../../../strings/index.js';
import { SEVERITY } from '../../../../vocab/severity.js';
import { KEY } from '../../../../vocab/keyboard.js';

const CLUSTER_HIT_PADDING = 40; // world units of fat-finger slack around a constellation's spread

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
  const rows = [row(t('map.score'), d.score.toFixed(1))];
  if (hovered.type === GALAXY_VIEW_HOVER_TYPE.DIM) rows.push(row(t('map.principles'), d.principleCount));
  rows.push(row(t('map.violations'), d.violations));
  if (d.violations > 0) {
    // For dimensions: compute severity from raw violations; for principles: use stored counts
    let sc = d.critical, sm = d.major, sn = d.minor;
    if (sc == null && d._raw?.violations) {
      sc = sm = sn = 0;
      (d._raw.violations || []).forEach(v => {
        const s = v.severity || SEVERITY.MINOR;
        if (s === SEVERITY.CRITICAL) sc++;
        else if (s === SEVERITY.MAJOR) sm++;
        else sn++;
      });
    }
    pushSeverityRows(rows, row, sc, sm, sn);
  }
  rows.push(row(t('map.compliance'), d.compliance));
  showTooltip(
    el,
    `<div style="font-weight:600;color:${rgb(d.col)};margin-bottom:4px">${escapeHtml(d.name)}</div>
    ${rows.join('')}
    <div style="margin-top:6px;color:var(--color-text-muted);font-size:11px;opacity:0.6">${escapeHtml(t('map.clickToExplore'))}</div>`,
    cx, cy,
  );
}

function navigateIntoHovered(h, nav, navigateTo) {
  if (nav.depth === 0 && h.type === GALAXY_VIEW_HOVER_TYPE.DIM) navigateTo(1, h.idx);
  else if (nav.depth === 1 && h.type === GALAXY_VIEW_HOVER_TYPE.PRIN) navigateTo(2, nav.dim, h.idx);
}

// The constellation whose hit circle contains the click, or null.
function clusterAt(e, { scene, size, w2s, camRef, canvasRef }) {
  const rect = canvasRef.current?.getBoundingClientRect();
  if (!rect) return null;
  const cmx = e.clientX - rect.left, cmy = e.clientY - rect.top;
  const zoom = camRef.current.z;
  const hit = scene.constellations.find((con) => {
    const csc = w2s(size.w / 2 + con.cx, size.h / 2 + con.cy);
    const dx = cmx - csc.x, dy = cmy - csc.y;
    const dist = Math.sqrt(dx * dx + dy * dy);
    return dist < (con.spread + CLUSTER_HIT_PADDING) * zoom;
  });
  return hit ?? null;
}

function leaveCluster(nav, startTransition, saveNav) {
  nav.clusterCx = null; nav.clusterCy = null;
  startTransition(true);
  saveNav();
}

// Clicking the cluster already zoomed into zooms back out to the galaxy.
function toggleCluster(con, nav, startTransition, saveNav) {
  if (nav.clusterCx === con.cx && nav.clusterCy === con.cy) {
    leaveCluster(nav, startTransition, saveNav);
    return;
  }
  nav.clusterCx = con.cx; nav.clusterCy = con.cy;
  startTransition(false);
  saveNav();
}

function navigateUp(nav, navigateTo) {
  if (nav.depth === 2) navigateTo(1, nav.dim);
  else navigateTo(0);
}

/**
 * Handle click on the galaxy canvas — navigate into stars/principles or zoom to clusters.
 *
 * @param {MouseEvent} e
 * @param {object} refs - { hoveredRef, navRef, animRef, camRef, canvasRef }
 * @param {object} params
 * @param {object} params.scene - The scene data
 * @param {object} params.size - { w, h }
 * @param {Function} params.navigateTo - (depth, dim, prin) => void
 * @param {Function} params.startTransition - (zoomingOut) => void
 * @param {Function} params.saveNav - () => void
 * @param {Function} params.w2s - World-to-screen transform
 */
export function handleCanvasClick(e, refs, { scene, size, navigateTo, startTransition, saveNav, w2s }) {
  const { hoveredRef, navRef, animRef, camRef, canvasRef } = refs;
  const h = hoveredRef.current;
  const nav = navRef.current;

  if (h) {
    navigateIntoHovered(h, nav, navigateTo);
    return;
  }

  // At galaxy root: a click near a cluster zooms to it (or back out of it).
  if (nav.depth === 0 && !animRef.current && scene?.constellations) {
    if (!camRef.current) return;
    const con = clusterAt(e, { scene, size, w2s, camRef, canvasRef });
    if (con) {
      toggleCluster(con, nav, startTransition, saveNav);
      return;
    }
  }

  // Click on empty space (outside any cluster).
  if (nav.depth > 0) navigateUp(nav, navigateTo);
  else if (nav.clusterCx != null) leaveCluster(nav, startTransition, saveNav);
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
function makeFocusAt({ scene, navRef, focusedIdxRef, announce }) {
  return (idx) => {
    const nodes = focusableNodes(scene, navRef.current);
    if (!nodes.length) return;
    const clamped = ((idx % nodes.length) + nodes.length) % nodes.length;
    focusedIdxRef.current = clamped;
    announceNode(announce, nodes[clamped], clamped, nodes.length);
  };
}

function makeMove({ scene, navRef, focusedIdxRef, focusAt }) {
  return (delta) => {
    const nodes = focusableNodes(scene, navRef.current);
    if (!nodes.length) return;
    const cur = focusedIdxRef.current;
    focusAt(cur === null ? (delta > 0 ? 0 : nodes.length - 1) : cur + delta);
  };
}

function makeActivate({ scene, navRef, focusedIdxRef, navigateTo, announce }) {
  return () => {
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
  };
}

function makeGoUp({ navRef, focusedIdxRef, navigateTo, startTransition, saveNav, announce }) {
  return () => {
    const nav = navRef.current;
    if (nav.depth === 2) { navigateTo(1, nav.dim); announce?.(t('map.returnedToPrinciples')); }
    else if (nav.depth === 1) { navigateTo(0); announce?.(t('map.returnedToOverview')); }
    else if (nav.clusterCx != null) {
      nav.clusterCx = null; nav.clusterCy = null;
      startTransition(true); saveNav();
      announce?.(t('map.returnedToOverview'));
    } else return false;
    focusedIdxRef.current = null;
    return true;
  };
}

function makeHandleKeyDown({ animRef, move, activate, goUp }) {
  return (e) => {
    if (animRef.current) return; // mid-transition: let the camera settle first
    switch (e.key) {
      case KEY.ARROW_RIGHT:
      case KEY.ARROW_DOWN:
        e.preventDefault(); move(1); break;
      case KEY.ARROW_LEFT:
      case KEY.ARROW_UP:
        e.preventDefault(); move(-1); break;
      case KEY.ENTER:
      case ' ':
        e.preventDefault(); activate(); break;
      case KEY.ESCAPE:
        if (goUp() !== false) e.preventDefault();
        break;
      default: break;
    }
  };
}

export function createKeyboardHandlers(refs, params) {
  const { navRef, animRef, focusedIdxRef } = refs;
  const { scene, navigateTo, startTransition, saveNav, announce } = params;

  const focusAt = makeFocusAt({ scene, navRef, focusedIdxRef, announce });
  const move = makeMove({ scene, navRef, focusedIdxRef, focusAt });
  const activate = makeActivate({ scene, navRef, focusedIdxRef, navigateTo, announce });
  const goUp = makeGoUp({ navRef, focusedIdxRef, navigateTo, startTransition, saveNav, announce });
  const handleKeyDown = makeHandleKeyDown({ animRef, move, activate, goUp });

  function handleFocus() {
    if (focusedIdxRef.current === null) focusAt(0);
  }

  function handleBlur() {
    focusedIdxRef.current = null;
  }

  return { handleKeyDown, handleFocus, handleBlur };
}
