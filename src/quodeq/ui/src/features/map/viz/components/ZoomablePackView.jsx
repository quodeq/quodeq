import { useMemo, useState, useCallback, useEffect, useRef } from 'react';
import { PACK_BASE_SIZE as BASE_SIZE, PACK_WORKER_NODE_THRESHOLD as PACK_CANVAS_NODE_THRESHOLD } from '../core/packLayout.js';
import { PACK_VIEW_PAD as PAD, screenCoordsFor } from '../core/packCanvasGeometry.js';
import PackCanvas from './PackCanvas.jsx';
import { usePackLayout } from '../core/usePackLayout.js';
import PackInfoPanel from './PackInfoPanel.jsx';
import PackCircles from './PackCircles.jsx';
import MapLegend from './MapLegend.jsx';
import { t } from '../../../../strings/index.js';
import { LABEL_GAP_PX } from './viewLabels.js';
import { KEY } from '../../../../vocab/keyboard.js';
import { PERCENT } from '../../../../constants.js';
import { isDrillableFolder } from '../core/fileTree.js';
import MapTooltipSeverityRows from './MapTooltipSeverityRows.jsx';
import FadeIn from '../../../../components/FadeIn.jsx';

const LABEL_RADIUS_THRESHOLD = 10;
const LABEL_FONT_MAX = 11;
const LABEL_FONT_MIN = 8;
const LABEL_FONT_DIVISOR = 4;
const TOOLTIP_OFFSET = 16;
const TOOLTIP_MAX_MARGIN = 180;
const TOOLTIP_MAX_MARGIN_Y = 160;
// Container size assumed while the element has not been measured yet, so
// the tooltip still clamps to something sane on the first hover.
const CONTAINER_FALLBACK_PX = 300;

function useFocusResetSync(resetKey, setFocus) {
  const prevResetKey = useRef(resetKey);
  useEffect(() => {
    if (resetKey !== prevResetKey.current) {
      prevResetKey.current = resetKey;
      setFocus(null);
    }
  }, [resetKey]);
}

// Sync focus to currentPath
function useFocusPathSync({ currentPath, circles, setFocus, skipTransition, prevPathRef }) {
  useEffect(() => {
    if (currentPath === prevPathRef.current) return;
    const isMount = prevPathRef.current === null;
    prevPathRef.current = currentPath;
    if (!currentPath) {
      if (!isMount) skipTransition.current = true;
      setFocus(null);
      if (!isMount) requestAnimationFrame(() => { skipTransition.current = false; });
    } else {
      const match = circles.find((c) => c.data.path === currentPath);
      if (match) {
        if (!isMount) skipTransition.current = true;
        setFocus(match);
        if (!isMount) requestAnimationFrame(() => { skipTransition.current = false; });
      }
    }
  }, [currentPath, circles]);
}

function useFocusTransform(focusNode) {
  return useMemo(() => {
    if (!focusNode) return { k: 1, tx: 0, ty: 0 };
    const k = BASE_SIZE / (focusNode.r * 2);
    const tx = BASE_SIZE / 2 - focusNode.x * k;
    const ty = BASE_SIZE / 2 - focusNode.y * k;
    return { k, tx, ty };
  }, [focusNode]);
}

function useScreenCoords(circles, k, tx, ty) {
  return useMemo(() => screenCoordsFor(circles, { k, tx, ty }), [circles, k, tx, ty]);
}

/**
 * Zoom out one level: focus the parent (or the root at the top) and report
 * the path that is now current.
 */
function focusParent(focusNode, { setFocus, onDrillDown, prevPathRef }) {
  const parent = focusNode?.parent;
  setFocus(parent || null);
  const parentPath = parent?.data?.path || '';
  onDrillDown?.(parentPath);
  prevPathRef.current = parentPath;
}

/** Drill into a folder circle and report the new current path. */
function focusFolder(c, { setFocus, onDrillDown, prevPathRef }) {
  setFocus(c);
  const path = c.data.path || '';
  onDrillDown?.(path);
  prevPathRef.current = path;
}

function useFocusHandlers({ focusNode, setFocus, onFileClick, onDrillDown, prevPathRef }) {
  const handleClick = useCallback((e, c) => {
    e.stopPropagation();
    const nav = { setFocus, onDrillDown, prevPathRef };
    const isFolder = isDrillableFolder(c.data);
    if (c.data.isFile) {
      onFileClick?.(c.data);
    } else if (isFolder && c !== focusNode) {
      focusFolder(c, nav);
    } else if (c === focusNode) {
      focusParent(focusNode, nav);
    }
  }, [focusNode, onFileClick, onDrillDown]);

  const handleBgClick = useCallback(() => {
    focusParent(focusNode, { setFocus, onDrillDown, prevPathRef });
  }, [focusNode, onDrillDown]);

  return { handleClick, handleBgClick };
}

// Pre-categorize circles
function useCircleIndices(circles) {
  return useMemo(() => {
    const fi = [], fli = [];
    circles.forEach((c, i) => {
      const d = c.data;
      const isFolder = isDrillableFolder(d);
      if (isFolder || c.depth === 0) fi.push(i);
      else fli.push(i);
    });
    return { folderIndices: fi, fileIndices: fli };
  }, [circles]);
}

/** The node to focus in the current layout. `focus` may belong to an
 * earlier hierarchy (the root is rebuilt on every view-mode switch and
 * worker reply); then the same path is looked up in the new circles. */
function useResolvedFocus(focus, root, circles) {
  return useMemo(() => {
    if (!focus) return root;
    if (focus.ancestors().at(-1) === root) return focus;
    return circles.find((c) => c.data.path === focus.data.path) || root;
  }, [focus, root, circles]);
}

/* ---- useFocusManager: focus state and click handling ---- */
function useFocusManager({ root, circles, resetKey, currentPath, onDrillDown, onFileClick }) {
  const [focus, setFocus] = useState(null);
  const skipTransition = useRef(true);
  const prevPathRef = useRef(null);

  useFocusResetSync(resetKey, setFocus);
  useFocusPathSync({ currentPath, circles, setFocus, skipTransition, prevPathRef });

  // Enable transitions after first paint
  useEffect(() => {
    requestAnimationFrame(() => { skipTransition.current = false; });
  }, []);

  const focusNode = useResolvedFocus(focus, root, circles);
  const transform = useFocusTransform(focusNode);
  const { k, tx, ty } = transform;
  const screenCoords = useScreenCoords(circles, k, tx, ty);
  const { handleClick, handleBgClick } = useFocusHandlers({ focusNode, setFocus, onFileClick, onDrillDown, prevPathRef });
  const { folderIndices, fileIndices } = useCircleIndices(circles);

  return { focusNode, k, tx, ty, transform, screenCoords, handleClick, handleBgClick, skipTransition, folderIndices, fileIndices };
}

/* ---- PackLabels: label rendering ---- */
function PackLabels({ circles, screenCoords, focusNode, skipTransition }) {
  return circles.map((c, i) => {
    const d = c.data;
    const isFolder = isDrillableFolder(d);
    const sc = screenCoords[i];
    if (!(sc.r > LABEL_RADIUS_THRESHOLD && c.parent === focusNode)) return null;
    return (
      <text
        key={'lbl-' + (d.path || i)}
        x={sc.cx} y={sc.cy - sc.r - LABEL_GAP_PX}
        textAnchor="middle" dominantBaseline="auto"
        style={{
          fontSize: Math.min(LABEL_FONT_MAX, Math.max(LABEL_FONT_MIN, sc.r / LABEL_FONT_DIVISOR)),
          fontFamily: 'var(--font-sans)',
          fill: 'var(--color-text)',
          pointerEvents: 'none',
          fontWeight: isFolder ? 'var(--weight-semibold)' : 'var(--weight-normal)',
          transition: skipTransition.current ? 'none' : 'x 0.5s ease, y 0.5s ease, font-size 0.5s ease',
        }}
      >
        {d.name.includes('/') ? d.name.split('/')[0] : d.name}
      </text>
    );
  });
}

/* ---- PackTooltip: tooltip ---- */
/** Tooltip position, clamped so it never runs off the container edge. */
function tooltipStyle(mousePos, containerRef) {
  const el = containerRef.current;
  return {
    position: 'absolute',
    left: Math.min(mousePos.current.x + TOOLTIP_OFFSET, (el?.offsetWidth || CONTAINER_FALLBACK_PX) - TOOLTIP_MAX_MARGIN),
    top: Math.min(mousePos.current.y + TOOLTIP_OFFSET, (el?.offsetHeight || CONTAINER_FALLBACK_PX) - TOOLTIP_MAX_MARGIN_Y),
    pointerEvents: 'none',
    zIndex: 10,
  };
}

/** Per-severity rows, shown only for a node that actually has violations. */
function TooltipSeverityRows({ hd }) {
  if (!(hd.violations > 0)) return null;
  return <MapTooltipSeverityRows severity={hd.severity} />;
}

function PackTooltip({ circles, hover, mousePos, containerRef }) {
  if (hover === null || !circles[hover] || circles[hover].depth === 0) return null;
  const hd = circles[hover].data;
  const total = hd.violations + hd.compliance;
  return (
    <div className="map-tooltip" style={tooltipStyle(mousePos, containerRef)}>
      <div className="map-tooltip-title">{(hd.path || hd.name || '').replace(/\/$/, '')}</div>
      <div className="map-tooltip-row"><span>{t('map.violations')}</span><span>{hd.violations}</span></div>
      <TooltipSeverityRows hd={hd} />
      <div className="map-tooltip-row"><span>{t('map.compliance')}</span><span>{hd.compliance}</span></div>
      <div className="map-tooltip-row"><span>{t('map.rate')}</span><span>{total > 0 ? ((hd.compliance / total) * PERCENT).toFixed(0) + '%' : '—'}</span></div>
    </div>
  );
}

/* ---- PackSvg: the SVG body, one node per circle ---- */
function PackSvg({ circles, viewMode, showLabels, hover, setHover, focus }) {
  const { focusNode, k, tx, ty, screenCoords, handleClick, handleBgClick, skipTransition, folderIndices, fileIndices } = focus;
  const transitionStyle = skipTransition.current ? 'none' : 'transform 0.5s ease';
  return (
    <svg
      className="viz-focusable"
      viewBox={`${-PAD} ${-PAD} ${BASE_SIZE + PAD * 2} ${BASE_SIZE + PAD * 2}`}
      style={{ width: '100%', height: '100%', overflow: 'hidden' }}
      tabIndex={0}
      onClick={handleBgClick}
      onKeyDown={(e) => { if (e.key === KEY.ESCAPE) { e.preventDefault(); handleBgClick(); } }}
      aria-label={t('map.zoomablePackAria')}
    >
      <defs>
        <filter id="glow" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="2" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>
      <g style={{ transform: `translate(${tx}px,${ty}px) scale(${k})`, transition: transitionStyle, willChange: 'transform', transformOrigin: '0 0' }}>
        <PackCircles circles={circles} folderIndices={folderIndices} fileIndices={fileIndices} hover={hover} setHover={setHover} viewMode={viewMode} k={k} handleClick={handleClick} />
      </g>
      {showLabels && <PackLabels circles={circles} screenCoords={screenCoords} focusNode={focusNode} skipTransition={skipTransition} />}
    </svg>
  );
}

/** Large packs draw on canvas: one SVG node per circle is what makes the
 * tab heavy, so past the layout-worker threshold the same circles paint in
 * a single element and keyboard users get a button per visible child. */
function PackBody({ circles, viewMode, showLabels, hover, setHover, focus }) {
  if (circles.length < PACK_CANVAS_NODE_THRESHOLD) {
    return <PackSvg circles={circles} viewMode={viewMode} showLabels={showLabels} hover={hover} setHover={setHover} focus={focus} />;
  }
  return (
    <PackCanvas
      circles={circles} transform={focus.transform} skipTransition={focus.skipTransition} viewMode={viewMode} hover={hover} setHover={setHover}
      focusNode={focus.focusNode} showLabels={showLabels} handleClick={focus.handleClick} handleBgClick={focus.handleBgClick}
    />
  );
}

/* ---- Main orchestrator ---- */
export default function ZoomablePackView({ node, viewMode, onDrillDown, onFileClick, showLabels = true, resetKey = 0, currentPath = '' }) {
  const [hover, setHover] = useState(null);
  const mousePos = useRef({ x: 0, y: 0 });
  const containerRef = useRef(null);

  const { root, circles } = usePackLayout(node, viewMode);
  const focus = useFocusManager({ root, circles, resetKey, currentPath, onDrillDown, onFileClick });

  if (!node) return null;
  const ready = circles.length > 0;

  return (
    <div ref={containerRef} style={{ position: 'relative', width: '100%', height: '100%', display: 'flex', justifyContent: 'center', alignItems: 'center' }} onMouseMove={(e) => { const r = containerRef.current?.getBoundingClientRect(); if (r) { mousePos.current = { x: e.clientX - r.left, y: e.clientY - r.top }; } }}>
      {/* The layout can land after the page fade (worker reply, view-mode
          switch), so the circles fade in on their own when a new root arrives.
          The wrapper stays mounted while a layout is pending so the fade
          restarts instead of resetting. */}
      <FadeIn restartKey={root} className="pack-fade">
        {ready && <PackBody circles={circles} viewMode={viewMode} showLabels={showLabels} hover={hover} setHover={setHover} focus={focus} />}
      </FadeIn>
      {ready && <PackTooltip circles={circles} hover={hover} mousePos={mousePos} containerRef={containerRef} />}
      {ready && <PackInfoPanel focusNode={focus.focusNode} root={root} onFileClick={onFileClick} />}
      {ready && <MapLegend />}
    </div>
  );
}
