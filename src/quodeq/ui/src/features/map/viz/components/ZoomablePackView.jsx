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
  const mousePos = useRef({ x: 0, y: 0 });
  const containerRef = useRef(null);
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

  // Pre-compute all transforms once per focus change
  const transformed = useMemo(() => {
    if (!focusNode) return circles.map(c => ({ cx: c.x, cy: c.y, r: c.r }));
    const k = viewSize / (focusNode.r * 2);
    const hv = viewSize / 2;
    return circles.map(c => ({
      cx: (c.x - focusNode.x) * k + hv,
      cy: (c.y - focusNode.y) * k + hv,
      r: c.r * k,
    }));
  }, [circles, focusNode, viewSize]);

  const transform = useCallback((c, i) => transformed[i] || { cx: c.x, cy: c.y, r: c.r }, [transformed]);

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

  // Level info panel — shows current focused node stats + View Details
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

  if (!node || !circles.length) return null;

  return (
    <div ref={containerRef} style={{ position: 'relative', width: '100%', height: '100%', display: 'flex', justifyContent: 'center', alignItems: 'center' }} onMouseMove={(e) => { const r = containerRef.current?.getBoundingClientRect(); if (r) { mousePos.current = { x: e.clientX - r.left, y: e.clientY - r.top }; } }}>
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
          const t = transform(c, i);
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
          const t = transform(c, i);
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
          const t = transform(c, i);
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
          <div className="map-tooltip" style={{ position: 'absolute', left: Math.min(mousePos.current.x + 16, (containerRef.current?.offsetWidth || 300) - 180), top: Math.min(mousePos.current.y + 16, (containerRef.current?.offsetHeight || 300) - 160), pointerEvents: 'none', zIndex: 10 }}>
            <div className="map-tooltip-title">{(hd.path || hd.name || '').replace(/\/$/, '')}</div>
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

      {/* Level info panel — fixed top-right */}
      {levelInfo && (
        <div style={{ position: 'absolute', top: 12, right: 16, background: 'color-mix(in srgb, var(--color-surface) 88%, transparent)', border: '1px solid var(--color-border)', borderRadius: 10, padding: '12px 18px', fontSize: 12, zIndex: 2, backdropFilter: 'blur(8px)', minWidth: 160 }}>
          <div style={{ fontWeight: 600, color: 'var(--color-text)', marginBottom: 8, fontSize: 13 }}>{levelInfo.title}</div>
          {levelInfo.lines.map((l, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', gap: 16, margin: '3px 0', color: l.color || 'var(--color-text-muted)' }}>
              <span>{l.label}</span>
              <span style={{ color: l.color || 'var(--color-text)', fontWeight: 500 }}>{l.value}</span>
            </div>
          ))}
          {levelInfo.detailAction && (
            <button
              type="button"
              onClick={levelInfo.detailAction}
              style={{ marginTop: 10, width: '100%', padding: '6px 12px', background: 'color-mix(in srgb, var(--color-accent) 20%, transparent)', border: '1px solid var(--color-border)', borderRadius: 6, color: 'var(--color-text)', fontSize: 11, cursor: 'pointer', transition: 'all 0.2s' }}
              onMouseEnter={e => { e.target.style.background = 'color-mix(in srgb, var(--color-accent) 35%, transparent)'; }}
              onMouseLeave={e => { e.target.style.background = 'color-mix(in srgb, var(--color-accent) 20%, transparent)'; }}
            >View Details</button>
          )}
        </div>
      )}

      {/* Legend — fixed bottom-left */}
      <div style={{ position: 'absolute', bottom: 8, left: 12, display: 'flex', gap: 14, fontSize: 11, color: 'var(--color-text-muted)', zIndex: 2 }}>
        {[
          { color: 'var(--color-grade-top-text)', label: 'Exemplary' },
          { color: 'var(--color-grade-high-text)', label: 'Good' },
          { color: 'var(--color-grade-mid-text)', label: 'Adequate' },
          { color: 'var(--color-grade-low-text)', label: 'Poor' },
          { color: 'var(--color-grade-bottom-text)', label: 'Critical' },
        ].map(({ color, label }) => (
          <span key={label} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, display: 'inline-block' }} />{label}
          </span>
        ))}
      </div>
    </div>
  );
}
