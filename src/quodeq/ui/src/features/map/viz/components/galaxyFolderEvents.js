import { getThemeColors, rgb } from '../core/galaxyCore.js';
import { escapeHtml } from '../../../../utils/escapeHtml.js';
import { buildFolderScene, countDescendants } from './galaxyFolderScene.js';

/**
 * Create mouse/click event handlers for GalaxyFolderView.
 * Returns { handleMouseMove, handleMouseLeave, handleClick, goToPathIndex, updateTooltip }.
 */
export function createEventHandlers(refs, params) {
  const {
    startTransition, saveNav, getFitZoom, scene, size,
  } = params;

  function updateTooltip(cx, cy) {
    const el = refs.tooltipRef.current;
    if (!el) return;
    const h = refs.hoveredRef.current;
    if (!h || refs.animRef.current) { el.style.display = 'none'; return; }
    const d = h.data;
    const row = (label, value, color) => `<div style="display:flex;justify-content:space-between;gap:12px;color:${color || 'var(--color-text-muted)'}"><span>${label}</span><span style="color:${color || 'var(--color-text)'};font-weight:500">${value}</span></div>`;
    const rows = [];
    const sev = d.severity || {};
    if (h.type === 'folder') {
      rows.push(row('Compliance', (d.complianceRate * 100).toFixed(0) + '%'));
      rows.push(row('Violations', d.violations));
      rows.push(row('Contents', countDescendants(d._node)));
    } else {
      rows.push(row('Violations', d.violations));
      rows.push(row('Compliance', d.compliance));
    }
    if (d.violations > 0) {
      if (sev.critical) rows.push(row('Critical', sev.critical, 'var(--color-sev-critical-text)'));
      if (sev.major) rows.push(row('Major', sev.major, 'var(--color-sev-major-text)'));
      if (sev.minor) rows.push(row('Minor', sev.minor, 'var(--color-sev-minor-text)'));
    }
    const nameCol = rgb(d.col);
    const name = d.name;
    const ff = refs.focusedFolderRef.current;
    const isFocused = h.type === 'folder' && ff && ff.starIdx === h.starIdx;
    const action = h.type === 'file' ? 'zoom in' : isFocused ? 'enter folder' : 'focus';
    el.innerHTML = `<div style="font-weight:600;color:${nameCol};margin-bottom:4px">${escapeHtml(name)}</div>${rows.join('')}<div style="margin-top:6px;color:var(--color-text-muted);font-size:11px;opacity:0.6">Click to ${action}</div>`;
    el.style.display = 'block';
    el.style.left = Math.min(cx + 16, window.innerWidth - 200) + 'px';
    el.style.top = Math.min(cy + 16, window.innerHeight - 160) + 'px';
  }

  function handleMouseMove(e) {
    const rect = refs.canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    refs.mouseRef.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    const h = refs.hoveredRef.current;
    refs.canvasRef.current.style.cursor = h ? 'pointer' : 'default';
    updateTooltip(e.clientX, e.clientY);
  }

  function handleMouseLeave() {
    refs.mouseRef.current = { x: -1, y: -1 };
    refs.hoveredRef.current = null;
    if (refs.tooltipRef.current) refs.tooltipRef.current.style.display = 'none';
  }

  function handleNodeClick(h) {
    if (h.type === 'folder') {
      const s = h.data;
      const ff = refs.focusedFolderRef.current;
      if (ff && ff.starIdx === h.starIdx) {
        return;
      } else {
        refs.zoomedFileRef.current = null;
        refs.zoomTargetRef.current = null;
        refs.focusedFolderRef.current = { x: s.x, y: s.y, starIdx: h.starIdx, data: s, autoEnter: true };
        startTransition(false);
        saveNav();
      }
      return;
    }
    if (h.type === 'file') {
      const s = h.data;
      refs.focusedFolderRef.current = null;
      refs.zoomTargetRef.current = null;
      refs.zoomedFileRef.current = { x: s.x, y: s.y, starIdx: h.starIdx, data: s };
      startTransition(false);
      saveNav();
    }
  }

  function handleEmptySpaceClick(nav) {
    if (refs.zoomedFileRef.current) {
      refs.zoomedFileRef.current = null;
      refs.zoomTargetRef.current = null;
      startTransition(true);
      saveNav();
    } else if (refs.zoomTargetRef.current) {
      refs.zoomTargetRef.current = null;
      startTransition(true);
      saveNav();
    } else if (refs.focusedFolderRef.current) {
      refs.focusedFolderRef.current = null;
      startTransition(true);
      saveNav();
    } else if (nav.path.length <= 1) {
      const cam = refs.camRef.current;
      if (cam && refs.mouseRef.current.x >= 0) {
        const wx = (refs.mouseRef.current.x - size.w / 2) / cam.z + cam.x;
        const wy = (refs.mouseRef.current.y - size.h / 2) / cam.z + cam.y;
        const curScene = refs.sceneRef.current || scene;
        let nearestStar = null, nearestD = Infinity;
        if (curScene) {
          curScene.rootStars.forEach(s => {
            const dx = s.x - wx, dy = s.y - wy;
            const d = dx * dx + dy * dy;
            if (d < nearestD) { nearestD = d; nearestStar = s; }
          });
        }
        const tx = nearestStar ? wx * 0.3 + nearestStar.x * 0.7 : wx;
        const ty = nearestStar ? wy * 0.3 + nearestStar.y * 0.7 : wy;
        const newZ = cam.z * 2.5;
        const maxZ = getFitZoom(curScene) * 10;
        refs.zoomTargetRef.current = { x: tx, y: ty, z: Math.min(newZ, maxZ) };
        startTransition(false);
        saveNav();
      }
    } else if (nav.path.length > 1) {
      if (refs.flyRef.current) return;
      const cam = refs.camRef.current;
      const parentPath = nav.path.slice(0, -1);
      const parentNode = parentPath[parentPath.length - 1];
      refs.nextSceneRef.current = buildFolderScene(parentNode, size.w, size.h);
      refs.flyRef.current = {
        t: 0, reverse: true,
        sx: cam.x, sy: cam.y, sz: cam.z,
        newPath: parentPath,
        starCol: getThemeColors().gradeMid,
        swapped: false,
      };
    }
  }

  function handleClick() {
    if (refs.animRef.current || refs.flyRef.current) return;
    const nav = refs.navRef.current;
    const h = refs.hoveredRef.current;

    if (h) {
      handleNodeClick(h);
      return;
    }

    handleEmptySpaceClick(nav);
  }

  function goToPathIndex(idx) {
    if (idx >= refs.navRef.current.path.length - 1 || refs.flyRef.current) return;
    const newPath = refs.navRef.current.path.slice(0, idx + 1);
    const targetNode = newPath[newPath.length - 1];
    const cam = refs.camRef.current;
    refs.nextSceneRef.current = buildFolderScene(targetNode, size.w, size.h);
    refs.flyRef.current = {
      t: 0, reverse: true,
      sx: cam.x, sy: cam.y, sz: cam.z,
      newPath,
      starCol: getThemeColors().gradeMid,
      swapped: false,
    };
  }

  const PAN_STEP = 40;

  function handleKeyDown(e) {
    const cam = refs.camRef.current;
    if (!cam) return;
    const z = cam.z || 1;
    const step = PAN_STEP / z;
    switch (e.key) {
      case 'ArrowLeft':
        e.preventDefault();
        cam.x -= step;
        break;
      case 'ArrowRight':
        e.preventDefault();
        cam.x += step;
        break;
      case 'ArrowUp':
        e.preventDefault();
        cam.y -= step;
        break;
      case 'ArrowDown':
        e.preventDefault();
        cam.y += step;
        break;
      case 'Enter':
      case ' ':
        e.preventDefault();
        handleClick();
        break;
      default:
        break;
    }
  }

  return { handleMouseMove, handleMouseLeave, handleClick, goToPathIndex, updateTooltip, handleKeyDown };
}
