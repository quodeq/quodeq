import { useMemo, useState, useCallback, useEffect, useRef } from 'react';
import { hierarchy, pack } from 'd3-hierarchy';
import { nodeColor, nodeBorderColor, nodeSize } from '../core/mapColors.js';
import FileShape from './FileShape.jsx';

const BASE_SIZE = 600;
const PAD = 20;
const FOLDER_STROKE_WIDTH = 1.5;
const FOLDER_FILL_OPACITY_HOVER = 0.3;
const FOLDER_FILL_OPACITY_DEFAULT = 0.2;
const LABEL_RADIUS_THRESHOLD = 10;
const LABEL_FONT_MAX = 11;
const LABEL_FONT_MIN = 8;
const LABEL_FONT_DIVISOR = 4;
const TOOLTIP_OFFSET = 16;
const TOOLTIP_MAX_MARGIN = 180;
const TOOLTIP_MAX_MARGIN_Y = 160;

/* ---- usePackLayout: d3 pack layout computation ---- */
function usePackLayout(node, viewMode) {
  return useMemo(() => {
    if (!node) return { root: null, circles: [] };
    const r = hierarchy(node, (d) => d.children || [])
      .sum((d) => (d.children?.length ? 0 : Math.max(1, nodeSize(d, viewMode))))
      .sort((a, b) => (b.value || 0) - (a.value || 0));
    if (!r.value) return { root: r, circles: [] };
    pack().size([BASE_SIZE, BASE_SIZE]).padding(6)(r);
    return { root: r, circles: r.descendants().filter((c) => c.r > 0) };
  }, [node, viewMode]);
}

/* ---- useFocusManager: focus state and click handling ---- */
function useFocusManager({ root, circles, resetKey, currentPath, onDrillDown, onFileClick }) {
  const [focus, setFocus] = useState(null);
  const skipTransition = useRef(true);
  const prevResetKey = useRef(resetKey);
  const prevPath = useRef(null);

  useEffect(() => {
    if (resetKey !== prevResetKey.current) {
      prevResetKey.current = resetKey;
      setFocus(null);
    }
  }, [resetKey]);

  // Sync focus to currentPath
  useEffect(() => {
    if (currentPath === prevPath.current) return;
    const isMount = prevPath.current === null;
    prevPath.current = currentPath;
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

  // Enable transitions after first paint
  useEffect(() => {
    requestAnimationFrame(() => { skipTransition.current = false; });
  }, []);

  const focusNode = focus || root;

  const { k, tx, ty } = useMemo(() => {
    if (!focusNode) return { k: 1, tx: 0, ty: 0 };
    const k = BASE_SIZE / (focusNode.r * 2);
    const tx = BASE_SIZE / 2 - focusNode.x * k;
    const ty = BASE_SIZE / 2 - focusNode.y * k;
    return { k, tx, ty };
  }, [focusNode]);

  const screenCoords = useMemo(() =>
    circles.map(c => ({
      cx: c.x * k + tx,
      cy: c.y * k + ty,
      r: c.r * k,
    })),
  [circles, k, tx, ty]);

  const handleClick = useCallback((e, c) => {
    e.stopPropagation();
    const isFolder = !c.data.isFile && c.data.children?.length > 0;
    if (c.data.isFile) {
      onFileClick?.(c.data);
    } else if (isFolder && c !== focusNode) {
      setFocus(c);
      onDrillDown?.(c.data.path || '');
      prevPath.current = c.data.path || '';
    } else if (c === focusNode) {
      const parent = focusNode?.parent;
      setFocus(parent || null);
      const parentPath = parent?.data?.path || '';
      onDrillDown?.(parentPath);
      prevPath.current = parentPath;
    }
  }, [focusNode, onFileClick, onDrillDown]);

  const handleBgClick = useCallback(() => {
    const parent = focusNode?.parent;
    setFocus(parent || null);
    const parentPath = parent?.data?.path || '';
    onDrillDown?.(parentPath);
    prevPath.current = parentPath;
  }, [focusNode, onDrillDown]);

  // Pre-categorize circles
  const { folderIndices, fileIndices } = useMemo(() => {
    const fi = [], fli = [];
    circles.forEach((c, i) => {
      const d = c.data;
      const isFolder = !d.isFile && d.children?.length > 0;
      if (isFolder || c.depth === 0) fi.push(i);
      else fli.push(i);
    });
    return { folderIndices: fi, fileIndices: fli };
  }, [circles]);

  return { focusNode, k, tx, ty, screenCoords, handleClick, handleBgClick, skipTransition, folderIndices, fileIndices };
}

/* ---- PackLabels: label rendering ---- */
function PackLabels({ circles, screenCoords, focusNode, skipTransition }) {
  return circles.map((c, i) => {
    const d = c.data;
    const isFolder = !d.isFile && d.children?.length > 0;
    const sc = screenCoords[i];
    if (!(sc.r > LABEL_RADIUS_THRESHOLD && c.parent === focusNode)) return null;
    return (
      <text
        key={'lbl-' + (d.path || i)}
        x={sc.cx} y={sc.cy - sc.r - 4}
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
function PackTooltip({ circles, hover, mousePos, containerRef }) {
  if (hover === null || !circles[hover] || circles[hover].depth === 0) return null;
  const hd = circles[hover].data;
  const sev = hd.severity || {};
  return (
    <div className="map-tooltip" style={{ position: 'absolute', left: Math.min(mousePos.current.x + TOOLTIP_OFFSET, (containerRef.current?.offsetWidth || 300) - TOOLTIP_MAX_MARGIN), top: Math.min(mousePos.current.y + TOOLTIP_OFFSET, (containerRef.current?.offsetHeight || 300) - TOOLTIP_MAX_MARGIN_Y), pointerEvents: 'none', zIndex: 10 }}>
      <div className="map-tooltip-title">{(hd.path || hd.name || '').replace(/\/$/, '')}</div>
      <div className="map-tooltip-row"><span>Violations</span><span>{hd.violations}</span></div>
      {hd.violations > 0 && sev.critical > 0 && <div className="map-tooltip-row" style={{ color: 'var(--color-sev-critical-text)' }}><span>Critical</span><span>{sev.critical}</span></div>}
      {hd.violations > 0 && sev.major > 0 && <div className="map-tooltip-row" style={{ color: 'var(--color-sev-major-text)' }}><span>Major</span><span>{sev.major}</span></div>}
      {hd.violations > 0 && sev.minor > 0 && <div className="map-tooltip-row" style={{ color: 'var(--color-sev-minor-text)' }}><span>Minor</span><span>{sev.minor}</span></div>}
      <div className="map-tooltip-row"><span>Compliance</span><span>{hd.compliance}</span></div>
      <div className="map-tooltip-row"><span>Rate</span><span>{(hd.violations + hd.compliance) > 0 ? ((hd.compliance / (hd.violations + hd.compliance)) * 100).toFixed(0) + '%' : '—'}</span></div>
    </div>
  );
}

/* ---- PackInfoPanel: info panel ---- */
function PackInfoPanel({ focusNode, root, onFileClick }) {
  const levelInfo = useMemo(() => {
    const fn = focusNode;
    if (!fn || !fn.data) return null;
    const d = fn.data;
    const isRoot = fn === root;
    const sev = d.severity || {};
    const rate = (d.violations + d.compliance) > 0
      ? Math.round((d.compliance / (d.violations + d.compliance)) * 100) + '%'
      : '—';
    const childFolders = (d.children || []).filter(c => !c.isFile && c.children?.length > 0).length;
    const childFiles = (d.children || []).filter(c => c.isFile || !c.children || c.children.length === 0).length;
    const lines = [
      { label: 'Compliance', value: rate },
      { label: 'Contents', value: childFolders + childFiles },
      { label: 'Violations', value: d.violations },
    ];
    if (d.violations > 0) {
      if (sev.critical > 0) lines.push({ label: 'Critical', value: sev.critical, color: 'var(--color-sev-critical-text)' });
      if (sev.major > 0) lines.push({ label: 'Major', value: sev.major, color: 'var(--color-sev-major-text)' });
      if (sev.minor > 0) lines.push({ label: 'Minor', value: sev.minor, color: 'var(--color-sev-minor-text)' });
    }
    const shortName = d.name?.includes('/') ? d.name.split('/')[0] : d.name;
    return {
      title: isRoot ? (d.name === '/' ? 'Project' : shortName) : shortName,
      lines,
      detailAction: !isRoot ? () => onFileClick?.(d) : null,
    };
  }, [focusNode, root, onFileClick]);

  if (!levelInfo) return null;

  return (
    <div style={{ position: 'absolute', top: 12, right: 16, background: 'color-mix(in srgb, var(--color-surface) 88%, transparent)', border: '1px solid var(--color-border)', borderRadius: 10, padding: '12px 18px', fontSize: 12, zIndex: 2, backdropFilter: 'blur(8px)', minWidth: 160 }}>
      <div style={{ fontWeight: 600, color: 'var(--color-text)', marginBottom: 8, fontSize: 13 }}>{levelInfo.title}</div>
      {levelInfo.lines.map((l, i) => (
        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', gap: 16, margin: '3px 0', color: l.color || 'var(--color-text-muted)' }}>
          <span>{l.label}</span>
          <span style={{ color: l.color || 'var(--color-text)', fontWeight: 500 }}>{l.value}</span>
        </div>
      ))}
      {levelInfo.detailAction && (
        <button type="button" onClick={levelInfo.detailAction}
          style={{ marginTop: 10, width: '100%', padding: '6px 12px', background: 'color-mix(in srgb, var(--color-accent) 20%, transparent)', border: '1px solid var(--color-border)', borderRadius: 6, color: 'var(--color-text)', fontSize: 11, cursor: 'pointer', transition: 'all 0.2s' }}
          onMouseEnter={e => { e.target.style.background = 'color-mix(in srgb, var(--color-accent) 35%, transparent)'; }}
          onMouseLeave={e => { e.target.style.background = 'color-mix(in srgb, var(--color-accent) 20%, transparent)'; }}
        >View Details</button>
      )}
    </div>
  );
}

/* ---- PackCircles: folder and file circle rendering ---- */
function PackCircles({ circles, folderIndices, fileIndices, hover, setHover, viewMode, k, handleClick }) {
  return (
    <>
      {folderIndices.map((i) => {
        const c = circles[i];
        const d = c.data;
        const isRoot = c.depth === 0;
        const isHovered = hover === i;
        return (
          <circle key={d.path || i} cx={c.x} cy={c.y} r={c.r}
            fill={isRoot ? 'var(--color-surface-alt)' : nodeColor(d, viewMode)}
            stroke={isRoot ? 'var(--color-border)' : nodeBorderColor(d, viewMode)}
            strokeWidth={FOLDER_STROKE_WIDTH} vectorEffect="non-scaling-stroke"
            fillOpacity={isRoot ? 1 : isHovered ? FOLDER_FILL_OPACITY_HOVER : FOLDER_FILL_OPACITY_DEFAULT}
            style={{ cursor: 'pointer', transition: 'fill-opacity 0.15s' }}
            onClick={(e) => handleClick(e, c)}
            onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}
          />
        );
      })}
      {fileIndices.map((i) => {
        const c = circles[i];
        const d = c.data;
        return (
          <FileShape key={d.path || i} cx={c.x} cy={c.y} r={c.r}
            color={nodeColor(d, viewMode)} borderColor={nodeBorderColor(d, viewMode)}
            glow={hover === i} parentScale={k}
            handlers={{ onClick: (e) => handleClick(e, c), onMouseEnter: () => setHover(i), onMouseLeave: () => setHover(null) }}
          />
        );
      })}
    </>
  );
}

/* ---- PackLegend: color legend ---- */
const LEGEND_ITEMS = [
  { color: 'var(--color-grade-top-text)', label: 'Exemplary' },
  { color: 'var(--color-grade-high-text)', label: 'Good' },
  { color: 'var(--color-grade-mid-text)', label: 'Adequate' },
  { color: 'var(--color-grade-low-text)', label: 'Poor' },
  { color: 'var(--color-grade-bottom-text)', label: 'Critical' },
];

/* ---- Main orchestrator ---- */
export default function ZoomablePackView({ node, viewMode, onDrillDown, onFileClick, showLabels = true, resetKey = 0, currentPath = '' }) {
  const [hover, setHover] = useState(null);
  const mousePos = useRef({ x: 0, y: 0 });
  const containerRef = useRef(null);

  const { root, circles } = usePackLayout(node, viewMode);
  const { focusNode, k, tx, ty, screenCoords, handleClick, handleBgClick, skipTransition, folderIndices, fileIndices } = useFocusManager({ root, circles, resetKey, currentPath, onDrillDown, onFileClick });

  if (!node || !circles.length) return null;

  const transitionStyle = skipTransition.current ? 'none' : 'transform 0.5s ease';

  return (
    <div ref={containerRef} style={{ position: 'relative', width: '100%', height: '100%', display: 'flex', justifyContent: 'center', alignItems: 'center' }} onMouseMove={(e) => { const r = containerRef.current?.getBoundingClientRect(); if (r) { mousePos.current = { x: e.clientX - r.left, y: e.clientY - r.top }; } }}>
      <svg
        viewBox={`${-PAD} ${-PAD} ${BASE_SIZE + PAD * 2} ${BASE_SIZE + PAD * 2}`}
        style={{ width: '100%', height: '100%', overflow: 'hidden' }}
        onClick={handleBgClick}
        aria-label="Zoomable pack visualization of project compliance by folder and file"
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
      <PackTooltip circles={circles} hover={hover} mousePos={mousePos} containerRef={containerRef} />
      <PackInfoPanel focusNode={focusNode} root={root} onFileClick={onFileClick} />
      <div style={{ position: 'absolute', bottom: 8, left: 12, display: 'flex', gap: 14, fontSize: 11, color: 'var(--color-text-muted)', zIndex: 2 }}>
        {LEGEND_ITEMS.map(({ color, label }) => (
          <span key={label} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, display: 'inline-block' }} />{label}
          </span>
        ))}
      </div>
    </div>
  );
}
