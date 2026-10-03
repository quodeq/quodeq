import { useEffect, useMemo, useRef } from 'react';
import ChartKeyboardControls from '../../../../components/ChartKeyboardControls.jsx';
import { useCanvasSize } from './galaxyCanvasSize.js';
import { drawPack } from '../core/packCanvasDraw.js';
import { packViewport, toLayoutPoint, hitCircle, screenCoordsFor } from '../core/packCanvasGeometry.js';
import { useTweenedTransform } from '../core/packTween.js';
import { nodeStateText } from '../core/mapColors.js';
import { t } from '../../../../strings/index.js';
import { KEY } from '../../../../vocab/keyboard.js';

// Keyboard stand-ins cover the current level only, capped like the galaxy
// views: one button per child of the focused folder.
const KBD_MAX = 100;
const NO_EVENT = { stopPropagation() {} };

function kbdItems(circles, focusNode, viewMode, handleClick) {
  const items = [];
  for (let i = 0; i < circles.length && items.length < KBD_MAX; i++) {
    const c = circles[i];
    if (c.parent !== focusNode) continue;
    const d = c.data;
    items.push({
      key: d.path || String(i),
      text: t('map.nodeStateAria', { name: d.name || d.path, state: nodeStateText(d, viewMode) }),
      onActivate: () => handleClick(NO_EVENT, c),
    });
  }
  return items;
}

function useDrawPack(canvasRef, size, frame) {
  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(size.w * dpr);
    canvas.height = Math.round(size.h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    drawPack(ctx, { ...frame, style: getComputedStyle(canvas), width: size.w, height: size.h });
  });
}

/**
 * Canvas renderer for packs too large to hold as SVG nodes. `transform` is
 * the focus target; the canvas tweens toward it. Hover and click
 * hit-test the cursor against the same circles the SVG path draws; keyboard
 * users get a focusable button per visible child (ChartKeyboardControls).
 */
export default function PackCanvas({ circles, transform, skipTransition, viewMode, hover, setHover, focusNode, showLabels, handleClick, handleBgClick }) {
  const canvasRef = useRef(null);
  const size = useCanvasSize(canvasRef);
  const viewport = useMemo(() => packViewport(size.w, size.h), [size.w, size.h]);
  // Zoom eases like the SVG view; hit tests use what is on screen right now.
  const shown = useTweenedTransform(transform, skipTransition);
  const screenCoords = useMemo(() => screenCoordsFor(circles, shown), [circles, shown]);
  const settled = shown === transform;

  useDrawPack(canvasRef, size, { circles, screenCoords, viewport, viewMode, hover, focusNode, showLabels: showLabels && settled });

  const hitAt = (e) => {
    const r = canvasRef.current.getBoundingClientRect();
    const p = toLayoutPoint(e.clientX - r.left, e.clientY - r.top, viewport);
    return hitCircle(circles, screenCoords, p.x, p.y);
  };
  const onMouseMove = (e) => {
    const i = hitAt(e);
    if (i !== hover) setHover(i);
  };
  const onClick = (e) => {
    const i = hitAt(e);
    if (i === null) handleBgClick();
    else handleClick(e, circles[i]);
  };

  return (
    <>
      <canvas
        ref={canvasRef}
        className="viz-focusable"
        tabIndex={0}
        aria-label={t('map.zoomablePackAria')}
        onKeyDown={(e) => { if (e.key === KEY.ESCAPE) { e.preventDefault(); handleBgClick(); } }}
        style={{ width: '100%', height: '100%', display: 'block', cursor: hover === null ? 'default' : 'pointer' }}
        onMouseMove={onMouseMove}
        onMouseLeave={() => setHover(null)}
        onClick={onClick}
      />
      <ChartKeyboardControls label={t('map.packKbdLabel')} items={kbdItems(circles, focusNode, viewMode, handleClick)} />
    </>
  );
}
