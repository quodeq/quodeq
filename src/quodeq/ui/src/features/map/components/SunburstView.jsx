import { useMemo, useState, useCallback } from 'react';
import { nodeColor, nodeSize } from '../utils/mapColors.js';

const MAX_DEPTH = 4;
const TAU = 2 * Math.PI;
const INNER_RADIUS = 0.18; // fraction of half-viewBox
const RING_WIDTH = 0.18;

function arcPath(cx, cy, innerR, outerR, startAngle, endAngle) {
  const span = endAngle - startAngle;
  const large = span > Math.PI ? 1 : 0;
  const cos = Math.cos, sin = Math.sin;
  const ix1 = cx + innerR * cos(startAngle), iy1 = cy + innerR * sin(startAngle);
  const ix2 = cx + innerR * cos(endAngle),   iy2 = cy + innerR * sin(endAngle);
  const ox1 = cx + outerR * cos(startAngle), oy1 = cy + outerR * sin(startAngle);
  const ox2 = cx + outerR * cos(endAngle),   oy2 = cy + outerR * sin(endAngle);
  if (span >= TAU - 0.001) {
    const mid = startAngle + Math.PI;
    const imx = cx + innerR * cos(mid), imy = cy + innerR * sin(mid);
    const omx = cx + outerR * cos(mid), omy = cy + outerR * sin(mid);
    return [
      `M${ox1},${oy1}`, `A${outerR},${outerR} 0 1,1 ${omx},${omy}`,
      `A${outerR},${outerR} 0 1,1 ${ox1},${oy1}`, `Z`,
      `M${ix1},${iy1}`, `A${innerR},${innerR} 0 1,0 ${imx},${imy}`,
      `A${innerR},${innerR} 0 1,0 ${ix1},${iy1}`, `Z`,
    ].join(' ');
  }
  return [
    `M${ox1},${oy1}`, `A${outerR},${outerR} 0 ${large},1 ${ox2},${oy2}`,
    `L${ix2},${iy2}`, `A${innerR},${innerR} 0 ${large},0 ${ix1},${iy1}`, `Z`,
  ].join(' ');
}

function flatten(node, viewMode, depth, startAngle, endAngle) {
  if (depth >= MAX_DEPTH) return [];
  const children = node.children || [];
  if (children.length === 0) return [];
  const totalSize = children.reduce((s, c) => s + nodeSize(c, viewMode), 0);
  if (totalSize === 0) return [];
  const arcs = [];
  let angle = startAngle;
  for (const child of children) {
    const size = nodeSize(child, viewMode);
    const span = ((endAngle - startAngle) * size) / totalSize;
    if (span < 0.003) { angle += span; continue; } // skip tiny arcs
    arcs.push({ node: child, depth, startAngle: angle, endAngle: angle + span });
    arcs.push(...flatten(child, viewMode, depth + 1, angle, angle + span));
    angle += span;
  }
  return arcs;
}

export default function SunburstView({ node, viewMode, onDrillDown }) {
  const [hover, setHover] = useState(null);

  const arcs = useMemo(
    () => (node ? flatten(node, viewMode, 0, -Math.PI / 2, TAU - Math.PI / 2) : []),
    [node, viewMode],
  );

  const handleClick = useCallback(
    (n) => { if (!n.isFile && n.children && n.children.length > 0) onDrillDown(n.path); },
    [onDrillDown],
  );

  if (!node) return null;

  const size = 500;
  const cx = size / 2, cy = size / 2;
  const unit = size / 2;
  const total = node.violations + node.compliance;
  const rate = total > 0 ? ((node.compliance / total) * 100).toFixed(0) : '—';

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', display: 'flex', justifyContent: 'center' }}>
      <svg viewBox={`0 0 ${size} ${size}`} style={{ width: '100%', maxWidth: 600, height: '100%' }}>
        {/* Center circle */}
        <circle cx={cx} cy={cy} r={unit * INNER_RADIUS} fill="var(--color-bg-elevated, #1e1e2e)" />
        <text x={cx} y={cy - 10} textAnchor="middle" dominantBaseline="central"
          style={{ fontSize: 13, fontWeight: 700, fill: 'var(--color-text, #fff)' }}>
          {node.name}
        </text>
        <text x={cx} y={cy + 10} textAnchor="middle" dominantBaseline="central"
          style={{ fontSize: 11, fill: 'var(--color-text-secondary, #aaa)' }}>
          {viewMode === 'health' ? `${rate}%` : `${node.violations}v · ${node.compliance}c`}
        </text>

        {arcs.map((a, i) => {
          const innerR = unit * (INNER_RADIUS + a.depth * RING_WIDTH);
          const outerR = unit * (INNER_RADIUS + (a.depth + 1) * RING_WIDTH);
          const d = arcPath(cx, cy, innerR, outerR, a.startAngle, a.endAngle);
          const color = nodeColor(a.node, viewMode);
          const isHovered = hover === i;
          const isFolder = !a.node.isFile && a.node.children && a.node.children.length > 0;
          return (
            <path key={i} d={d}
              fill={color} stroke="var(--color-bg, #111)" strokeWidth={1.2}
              opacity={isHovered ? 1 : 0.82}
              style={{ cursor: isFolder ? 'pointer' : 'default', transition: 'opacity 0.15s' }}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
              onClick={() => isFolder && handleClick(a.node)}
            />
          );
        })}
      </svg>

      {hover !== null && arcs[hover] && (
        <Tooltip node={arcs[hover].node} />
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
