import { useMemo, useState, useCallback } from 'react';
import { hierarchy, pack } from 'd3-hierarchy';
import { nodeColor, nodeSize } from '../utils/mapColors.js';

const BASE_SIZE = 600;

export default function ZoomablePackView({ node, viewMode, onDrillDown, zoom = 1 }) {
  const [focus, setFocus] = useState(null);
  const [hover, setHover] = useState(null);

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
    if (isFolder && c !== focusNode) {
      setFocus(c);
    } else if (c === focusNode || !isFolder) {
      setFocus(focusNode?.parent || null);
    }
  }, [focusNode]);

  const handleBgClick = useCallback(() => {
    setFocus(focusNode?.parent || null);
  }, [focusNode]);

  if (!node || !circles.length) return null;

  return (
    <div style={{ position: 'relative', width: '100%', display: 'flex', justifyContent: 'center' }}>
      <svg
        viewBox={`0 0 ${viewSize} ${viewSize}`}
        style={{ width: viewSize, height: viewSize, maxWidth: 'none', overflow: 'hidden' }}
        onClick={handleBgClick}
      >
        {circles.map((c, i) => {
          const d = c.data;
          const isFolder = !d.isFile && d.children?.length > 0;
          const isRoot = c.depth === 0;
          const t = transform(c);
          // Only show labels at current level: direct children of the focused node
          const showLabel = t.r > 10 && c.parent === focusNode;
          const isHovered = hover === i;
          return (
            <g
              key={d.path || i}
              onClick={(e) => handleClick(e, c)}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
              style={{ cursor: isFolder ? 'pointer' : 'default' }}
            >
              <circle
                cx={t.cx} cy={t.cy} r={t.r}
                fill={isRoot ? 'var(--color-bg-elevated, #1e1e2e)' : nodeColor(d, viewMode)}
                stroke={isFolder ? 'var(--color-border, #444)' : 'none'}
                strokeWidth={isFolder ? 1.5 : 0}
                fillOpacity={isFolder && !isRoot ? 0.2 : isHovered ? 1 : 0.82}
                style={{ transition: 'cx 0.5s ease, cy 0.5s ease, r 0.5s ease, fill-opacity 0.15s' }}
              />
              {showLabel && (
                <text
                  x={t.cx} y={t.cy}
                  textAnchor="middle" dominantBaseline="central"
                  style={{
                    fontSize: Math.min(13, t.r / 3),
                    fill: 'var(--color-text, #fff)',
                    pointerEvents: 'none',
                    fontWeight: isFolder ? 700 : 400,
                    transition: 'x 0.5s ease, y 0.5s ease, font-size 0.5s ease',
                  }}
                >
                  {d.name}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      {hover !== null && circles[hover] && circles[hover].depth > 0 && (
        <div className="map-tooltip" style={{ position: 'absolute', top: 8, right: 8, pointerEvents: 'none' }}>
          <div className="map-tooltip-title">{circles[hover].data.path || circles[hover].data.name}</div>
          <div className="map-tooltip-row">
            <span>Violations</span><span>{circles[hover].data.violations}</span>
          </div>
          <div className="map-tooltip-row">
            <span>Compliance</span><span>{circles[hover].data.compliance}</span>
          </div>
          <div className="map-tooltip-row">
            <span>Rate</span>
            <span>
              {(circles[hover].data.violations + circles[hover].data.compliance) > 0
                ? ((circles[hover].data.compliance / (circles[hover].data.violations + circles[hover].data.compliance)) * 100).toFixed(0) + '%'
                : '—'}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
