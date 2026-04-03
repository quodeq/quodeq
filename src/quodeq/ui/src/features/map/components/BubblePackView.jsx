import { useMemo, useState, useCallback } from 'react';
import { hierarchy, pack } from 'd3-hierarchy';
import { nodeColor, nodeSize } from '../utils/mapColors.js';

const MAX_DEPTH = 3;
const BASE_SIZE = 500;

export default function BubblePackView({ node, viewMode, onDrillDown, zoom = 1 }) {
  const [hover, setHover] = useState(null);

  const circles = useMemo(() => {
    if (!node || (!node.children?.length && !node.violations && !node.compliance)) return [];
    const root = hierarchy(node, (d) => d.children || [])
      .sum((d) => {
        // Leaves get their size; folders get 0 (d3 accumulates from leaves)
        if (d.children && d.children.length > 0) return 0;
        return Math.max(1, nodeSize(d, viewMode)); // ensure positive value
      })
      .sort((a, b) => (b.value || 0) - (a.value || 0));

    if (!root.value) return []; // nothing to pack

    const viewSize = Math.round(BASE_SIZE * zoom);
    const layout = pack().size([viewSize, viewSize]).padding(4);
    layout(root);
    return root.descendants()
      .filter((c) => c.depth <= MAX_DEPTH && c.r > 0 && !isNaN(c.r));
  }, [node, viewMode, zoom]);

  const viewSize = Math.round(BASE_SIZE * zoom);

  const handleClick = useCallback(
    (n) => { if (!n.isFile && n.children && n.children.length > 0) onDrillDown(n.path); },
    [onDrillDown],
  );

  if (!node) return null;

  return (
    <div style={{ position: 'relative', width: '100%', display: 'flex', justifyContent: 'center' }}>
      <svg viewBox={`0 0 ${viewSize} ${viewSize}`} style={{ width: viewSize, height: viewSize, maxWidth: 'none' }}>
        {circles.map((c, i) => {
          const d = c.data;
          const isFolder = !d.isFile && d.children && d.children.length > 0;
          const isRoot = c.depth === 0;
          const isHovered = hover === i;
          return (
            <g key={i}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
              onClick={() => isFolder && handleClick(d)}
              style={{ cursor: isFolder ? 'pointer' : 'default' }}
            >
              <circle
                cx={c.x} cy={c.y} r={c.r}
                fill={isRoot ? 'var(--color-bg-elevated, #1e1e2e)' : nodeColor(d, viewMode)}
                stroke={isFolder ? 'var(--color-border, #444)' : 'none'}
                strokeWidth={isFolder ? 1.2 : 0}
                fillOpacity={isFolder && !isRoot ? 0.25 : isHovered ? 1 : 0.82}
                style={{ transition: 'fill-opacity 0.15s' }}
              />
              {c.r > 20 && (
                <text
                  x={c.x} y={c.y}
                  textAnchor="middle" dominantBaseline="central"
                  style={{
                    fontSize: Math.min(11, c.r / 3),
                    fill: 'var(--color-text, #fff)',
                    pointerEvents: 'none',
                    fontWeight: isFolder ? 700 : 400,
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
        <Tooltip node={circles[hover].data} />
      )}
    </div>
  );
}

function Tooltip({ node }) {
  const total = node.violations + node.compliance;
  const rate = total > 0 ? ((node.compliance / total) * 100).toFixed(0) : '—';
  return (
    <div className="map-tooltip" style={{ position: 'absolute', top: 8, right: 8, pointerEvents: 'none' }}>
      <div className="map-tooltip-title">{node.path || node.name}</div>
      <div className="map-tooltip-row"><span>Violations</span><span>{node.violations}</span></div>
      <div className="map-tooltip-row"><span>Compliance</span><span>{node.compliance}</span></div>
      <div className="map-tooltip-row"><span>Compliance rate</span><span>{rate}%</span></div>
      {node.severity && (
        <>
          {node.severity.critical > 0 && <div className="map-tooltip-row"><span>Critical</span><span>{node.severity.critical}</span></div>}
          {node.severity.major > 0 && <div className="map-tooltip-row"><span>Major</span><span>{node.severity.major}</span></div>}
          {node.severity.minor > 0 && <div className="map-tooltip-row"><span>Minor</span><span>{node.severity.minor}</span></div>}
        </>
      )}
    </div>
  );
}
