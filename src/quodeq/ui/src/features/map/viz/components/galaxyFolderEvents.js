import { getThemeColors } from '../core/galaxyCore.js';
import { buildFolderScene } from './galaxyFolderScene.js';
import { createTooltipUpdater } from './galaxyFolderTooltip.js';
import { handleNodeClick, handleEmptySpaceClick } from './galaxyFolderClickHandlers.js';

function makeMouseMoveHandler(refs, updateTooltip) {
  return function handleMouseMove(e) {
    const rect = refs.canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    refs.mouseRef.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    const h = refs.hoveredRef.current;
    refs.canvasRef.current.style.cursor = h ? 'pointer' : 'default';
    updateTooltip(e.clientX, e.clientY);
  };
}

function makeMouseLeaveHandler(refs) {
  return function handleMouseLeave() {
    refs.mouseRef.current = { x: -1, y: -1 };
    refs.hoveredRef.current = null;
    if (refs.tooltipRef.current) refs.tooltipRef.current.style.display = 'none';
  };
}

function makeClickHandler(refs, params) {
  const { startTransition, saveNav, getFitZoom, scene, size } = params;
  return function handleClick() {
    if (refs.animRef.current || refs.flyRef.current) return;
    const nav = refs.navRef.current;
    const h = refs.hoveredRef.current;

    if (h) {
      handleNodeClick(refs, h, { startTransition, saveNav });
      return;
    }

    handleEmptySpaceClick(refs, nav, { startTransition, saveNav, getFitZoom, scene, size });
  };
}

function makeGoToPathIndexHandler(refs, size) {
  return function goToPathIndex(idx) {
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
  };
}

const PAN_STEP = 40;

function makeKeyDownHandler(refs, handleClick) {
  return function handleKeyDown(e) {
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
  };
}

/**
 * Create mouse/click event handlers for GalaxyFolderView.
 * Returns { handleMouseMove, handleMouseLeave, handleClick, goToPathIndex, updateTooltip, handleKeyDown }.
 */
export function createEventHandlers(refs, params) {
  const { size } = params;
  const updateTooltip = createTooltipUpdater(refs);
  const handleMouseMove = makeMouseMoveHandler(refs, updateTooltip);
  const handleMouseLeave = makeMouseLeaveHandler(refs);
  const handleClick = makeClickHandler(refs, params);
  const goToPathIndex = makeGoToPathIndexHandler(refs, size);
  const handleKeyDown = makeKeyDownHandler(refs, handleClick);

  return { handleMouseMove, handleMouseLeave, handleClick, goToPathIndex, updateTooltip, handleKeyDown };
}
