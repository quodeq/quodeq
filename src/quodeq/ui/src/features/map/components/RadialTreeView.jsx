import { useState, useMemo } from 'react';
import { nodeColor } from '../utils/mapColors.js';

const BASE_SIZE = 500;
const RADIUS_STEP = 90;

function buildLayout(node, angle, spread, depth, cx, cy) {
  const r = depth * RADIUS_STEP;
  const x = depth === 0 ? cx : cx + r * Math.cos(angle);
  const y = depth === 0 ? cy : cy + r * Math.sin(angle);
  const result = { node, x, y, depth, angle, children: [] };

  const kids = node.children || [];
  if (kids.length > 0) {
    const step = spread / kids.length;
    const start = angle - spread / 2 + step / 2;
    for (let i = 0; i < kids.length; i++) {
      result.children.push(
        buildLayout(kids[i], start + i * step, Math.max(step, Math.PI / 6), depth + 1, cx, cy)
      );
    }
  }
  return result;
}

function cubicPath(x1, y1, x2, y2) {
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;
  return `M${x1},${y1} Q${mx},${my} ${x2},${y2}`;
}

function Nodes({ layout, viewMode, onDrillDown, collapsed, onToggle, tooltip, setTooltip }) {
  const { node, x, y, depth, children } = layout;
  const r = Math.sqrt((node.violations || 0) + 1) * 3 + 3;
  const color = nodeColor(node, viewMode);
  const hasKids = (node.children || []).length > 0;
  const isCollapsed = collapsed.has(node.path || node.name);
  const labelAngle = layout.angle ?? 0;
  const flip = Math.cos(labelAngle) < 0;
  const lx = x + (r + 5) * (flip ? -1 : 1);
  const labelAnchor = flip ? 'end' : 'start';

  return (
    <g>
      {depth > 0 && (
        <path d={cubicPath(layout.px, layout.py, x, y)}
          fill="none" stroke="var(--color-border, #444)" strokeWidth={1} strokeOpacity={0.6} />
      )}
      {!isCollapsed && children.map((ch) => (
        <Nodes key={ch.node.path || ch.node.name} layout={{ ...ch, px: x, py: y }}
          viewMode={viewMode} onDrillDown={onDrillDown}
          collapsed={collapsed} onToggle={onToggle}
          tooltip={tooltip} setTooltip={setTooltip} />
      ))}
      <circle cx={x} cy={y} r={r} fill={color}
        stroke={hasKids ? 'var(--color-border, #888)' : 'none'} strokeWidth={hasKids ? 1.5 : 0}
        style={{ cursor: 'pointer' }}
        onClick={() => { hasKids ? onToggle(node.path || node.name) : onDrillDown(node.path); }}
        onMouseEnter={(e) => setTooltip({ x: e.clientX, y: e.clientY, node })}
        onMouseLeave={() => setTooltip(null)} />
      <text x={lx} y={y} dy="0.35em" fontSize={10} fill="var(--color-text-muted, #aaa)"
        textAnchor={labelAnchor} style={{ pointerEvents: 'none', userSelect: 'none' }}>
        {node.name}
      </text>
    </g>
  );
}

export default function RadialTreeView({ node, viewMode, onDrillDown, zoom = 1 }) {
  const [collapsed, setCollapsed] = useState(new Set());
  const [tooltip, setTooltip] = useState(null);

  const size = BASE_SIZE * zoom;
  const cx = size / 2;
  const cy = size / 2;

  const layout = useMemo(
    () => buildLayout(node, -Math.PI / 2, 2 * Math.PI, 0, cx, cy),
    [node, cx, cy]
  );

  function toggleCollapse(path) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      next.has(path) ? next.delete(path) : next.add(path);
      return next;
    });
  }

  return (
    <div style={{ position: 'relative', display: 'inline-block' }}>
      <svg width={size} height={size} style={{ display: 'block' }}>
        <Nodes layout={{ ...layout, px: cx, py: cy }}
          viewMode={viewMode} onDrillDown={onDrillDown}
          collapsed={collapsed} onToggle={toggleCollapse}
          tooltip={tooltip} setTooltip={setTooltip} />
      </svg>
      {tooltip && (
        <div className="map-tooltip" style={{
          position: 'fixed', left: tooltip.x + 12, top: tooltip.y - 8,
          pointerEvents: 'none', zIndex: 9999,
        }}>
          <div className="map-tooltip__name">{tooltip.node.name}</div>
          <div className="map-tooltip__stat">Violations: {tooltip.node.violations ?? 0}</div>
          <div className="map-tooltip__stat">Compliance: {((tooltip.node.complianceRate ?? 0) * 100).toFixed(0)}%</div>
        </div>
      )}
    </div>
  );
}
