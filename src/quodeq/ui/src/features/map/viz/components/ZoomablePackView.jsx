import { useMemo, useState, useCallback, useEffect, useRef } from 'react';
import { hierarchy, pack } from 'd3-hierarchy';
import { nodeColor, nodeBorderColor, nodeSize } from '../core/mapColors.js';
import FileShape from './FileShape.jsx';

const BASE_SIZE = 600;
let _savedFocusPath = null;

export function resetSavedFocus() { _savedFocusPath = null; }

export default function ZoomablePackView({ node, viewMode, onDrillDown, onFileClick, showLabels = true, zoom = 1, resetKey = 0 }) {
  const [focus, _setFocus] = useState(null);
  const setFocus = (n) => { _savedFocusPath = n?.data?.path || null; _setFocus(n); };

  // Zoom out to root with transition when resetKey changes
  const prevResetKey = useRef(resetKey);
  useEffect(() => {
    if (resetKey !== prevResetKey.current) {
      prevResetKey.current = resetKey;
      _savedFocusPath = null;
      _setFocus(null);
    }
  }, [resetKey]);
  const [hover, setHover] = useState(null);
  const skipTransition = useRef(!!_savedFocusPath);

  const { root, circles } = useMemo(() => {
    if (!node) return { root: null, circles: [] };
    const r = hierarchy(node, (d) => d.children || [])
      .sum((d) => (d.children?.length ? 0 : Math.max(1, nodeSize(d, viewMode))))
      .sort((a, b) => (b.value || 0) - (a.value || 0));
    if (!r.value) return { root: r, circles: [] };
    const size = Math.round(BASE_SIZE * zoom);
    pack().size([size, size]).padding(6)(r);
    return { root: r, circles: r.descendants().filter((c) => c.r > 0) };
  }, [node, viewMode, zoom]);

  // Restore focus from saved path on mount (skip transition)
  useEffect(() => {
    if (_savedFocusPath && circles.length > 0 && !focus) {
      const match = circles.find((c) => c.data.path === _savedFocusPath);
      if (match) _setFocus(match);
      // Keep skipTransition true until the restored focus is rendered
      return;
    }
    // Allow transitions after focus has been restored and painted
    if (skipTransition.current) {
      requestAnimationFrame(() => { skipTransition.current = false; });
    }
  }, [circles, focus]);

  const focusNode = focus || root;
  const viewSize = Math.round(BASE_SIZE * zoom);

  const transform = useCallback((c) => {
    if (!focusNode) return { cx: c.x, cy: c.y, r: c.r };
    const k = viewSize / (focusNode.r * 2);
    return {
      cx: (c.x - focusNode.x) * k + viewSize / 2,
      cy: (c.y - focusNode.y) * k + viewSize / 2,
      r: c.r * k,
    };
  }, [focusNode, viewSize]);

  const handleClick = useCallback((e, c) => {
    e.stopPropagation();
    const isFolder = !c.data.isFile && c.data.children?.length > 0;
    if (c.data.isFile) {
      onFileClick?.(c.data);
    } else if (isFolder && c !== focusNode) {
      setFocus(c);
    } else if (c === focusNode) {
      setFocus(focusNode?.parent || null);
    }
  }, [focusNode, onFileClick]);

  const handleBgClick = useCallback(() => {
    setFocus(focusNode?.parent || null);
  }, [focusNode]);

  if (!node || !circles.length) return null;

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
      <svg
        viewBox={`-20 -20 ${viewSize + 40} ${viewSize + 40}`}
        style={{ width: '100%', height: '100%', overflow: 'hidden' }}
        onClick={handleBgClick}
      >
        {/* Layer 1: folders (circles) */}
        {circles.map((c, i) => {
          const d = c.data;
          const isFolder = !d.isFile && d.children?.length > 0;
          const isRoot = c.depth === 0;
          if (!isFolder && !isRoot) return null;
          const t = transform(c);
          const isHovered = hover === i;
          return (
            <circle
              key={d.path || i}
              cx={t.cx} cy={t.cy} r={t.r}
              fill={isRoot ? 'var(--color-surface-alt)' : nodeColor(d, viewMode)}
              stroke={isRoot ? 'var(--color-border)' : nodeBorderColor(d, viewMode)}
              strokeWidth={1.5}
              fillOpacity={isRoot ? 1 : isHovered ? 0.3 : 0.2}
              style={{ cursor: 'pointer', transition: skipTransition.current ? 'none' : 'cx 0.5s ease, cy 0.5s ease, r 0.5s ease, fill-opacity 0.15s' }}
              onClick={(e) => handleClick(e, c)}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
            />
          );
        })}
        {/* Layer 2: files (document icons) */}
        {circles.map((c, i) => {
          const d = c.data;
          const isFolder = !d.isFile && d.children?.length > 0;
          if (isFolder || c.depth === 0) return null;
          const t = transform(c);
          return (
            <FileShape
              key={d.path || i}
              cx={t.cx} cy={t.cy} r={t.r}
              color={nodeColor(d, viewMode)}
              borderColor={nodeBorderColor(d, viewMode)}
              glow={hover === i}
              transition={!skipTransition.current}
              handlers={{
                onClick: (e) => handleClick(e, c),
                onMouseEnter: () => setHover(i),
                onMouseLeave: () => setHover(null),
              }}
            />
          );
        })}
        {/* Layer 3: labels on top of all circles */}
        {showLabels && circles.map((c, i) => {
          const d = c.data;
          const isFolder = !d.isFile && d.children?.length > 0;
          const t = transform(c);
          if (!(t.r > 10 && c.parent === focusNode)) return null;
          return (
            <text
              key={'lbl-' + (d.path || i)}
              x={t.cx} y={t.cy - t.r - 4}
              textAnchor="middle" dominantBaseline="auto"
              style={{
                fontSize: Math.min(11, Math.max(8, t.r / 4)),
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
        })}
      </svg>

      {hover !== null && circles[hover] && circles[hover].depth > 0 && (() => {
        const hd = circles[hover].data;
        const sev = hd.severity || {};
        return (
          <div className="map-tooltip" style={{ position: 'absolute', top: 8, right: 8, pointerEvents: 'none' }}>
            <div className="map-tooltip-title">{hd.path || hd.name}</div>
            <div className="map-tooltip-row">
              <span>Violations</span><span>{hd.violations}</span>
            </div>
            {hd.violations > 0 && sev.critical > 0 && (
              <div className="map-tooltip-row" style={{ color: 'var(--color-sev-critical-text)' }}>
                <span>Critical</span><span>{sev.critical}</span>
              </div>
            )}
            {hd.violations > 0 && sev.major > 0 && (
              <div className="map-tooltip-row" style={{ color: 'var(--color-sev-major-text)' }}>
                <span>Major</span><span>{sev.major}</span>
              </div>
            )}
            {hd.violations > 0 && sev.minor > 0 && (
              <div className="map-tooltip-row" style={{ color: 'var(--color-sev-minor-text)' }}>
                <span>Minor</span><span>{sev.minor}</span>
              </div>
            )}
            <div className="map-tooltip-row">
              <span>Compliance</span><span>{hd.compliance}</span>
            </div>
            <div className="map-tooltip-row">
              <span>Rate</span>
              <span>
                {(hd.violations + hd.compliance) > 0
                  ? ((hd.compliance / (hd.violations + hd.compliance)) * 100).toFixed(0) + '%'
                  : '—'}
              </span>
            </div>
          </div>
        );
      })()}
    </div>
  );
}
