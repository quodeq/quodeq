import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { nodeColor } from '../utils/mapColors.js';

const BASE_SIZE = 500;

function flattenTree(root, nodes = [], links = []) {
  const id = root.path || root.name;
  nodes.push({ ...root, id, x: Math.random() * 400 - 200, y: Math.random() * 400 - 200, vx: 0, vy: 0 });
  for (const child of root.children || []) {
    links.push({ source: id, target: child.path || child.name });
    flattenTree(child, nodes, links);
  }
  return { nodes, links };
}

function simulate(nodes, links, iterations = 120) {
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
  for (let t = 0; t < iterations; t++) {
    const alpha = 1 - t / iterations;
    // repulsion
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        let dx = b.x - a.x || 0.1, dy = b.y - a.y || 0.1;
        const d2 = dx * dx + dy * dy, d = Math.sqrt(d2);
        const f = (800 * alpha) / Math.max(d2, 1);
        a.vx -= (dx / d) * f; a.vy -= (dy / d) * f;
        b.vx += (dx / d) * f; b.vy += (dy / d) * f;
      }
    }
    // attraction along links
    for (const l of links) {
      const s = byId[l.source], t2 = byId[l.target];
      if (!s || !t2) continue;
      let dx = t2.x - s.x, dy = t2.y - s.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 1;
      const f = (d - 40) * 0.05 * alpha;
      s.vx += (dx / d) * f; s.vy += (dy / d) * f;
      t2.vx -= (dx / d) * f; t2.vy -= (dy / d) * f;
    }
    // center gravity + velocity integration
    for (const n of nodes) {
      n.vx -= n.x * 0.01 * alpha;
      n.vy -= n.y * 0.01 * alpha;
      n.vx *= 0.6; n.vy *= 0.6;
      n.x += n.vx; n.y += n.vy;
    }
  }
  return nodes;
}

export default function ForceGraphView({ node, viewMode, onDrillDown, zoom = 1 }) {
  const [hover, setHover] = useState(null);
  const [dragId, setDragId] = useState(null);
  const svgRef = useRef(null);

  const { nodes, links, byId } = useMemo(() => {
    if (!node) return { nodes: [], links: [], byId: {} };
    const { nodes: rawNodes, links: rawLinks } = flattenTree(node);
    simulate(rawNodes, rawLinks);
    return { nodes: rawNodes, links: rawLinks, byId: Object.fromEntries(rawNodes.map((n) => [n.id, n])) };
  }, [node]);

  const [positions, setPositions] = useState(() => Object.fromEntries(nodes.map((n) => [n.id, { x: n.x, y: n.y }])));

  useEffect(() => {
    setPositions(Object.fromEntries(nodes.map((n) => [n.id, { x: n.x, y: n.y }])));
  }, [nodes]);

  const viewSize = Math.round(BASE_SIZE * zoom);
  const half = viewSize / 2;

  const handleMouseDown = useCallback((e, id) => {
    e.stopPropagation();
    setDragId(id);
  }, []);

  const handleMouseMove = useCallback((e) => {
    if (!dragId || !svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * viewSize - half;
    const y = ((e.clientY - rect.top) / rect.height) * viewSize - half;
    setPositions((p) => ({ ...p, [dragId]: { x, y } }));
  }, [dragId, viewSize, half]);

  const handleMouseUp = useCallback(() => setDragId(null), []);

  const handleClick = useCallback((n) => {
    if (!n.isFile && onDrillDown) onDrillDown(n.path);
  }, [onDrillDown]);

  const hoverNode = hover ? byId[hover] : null;
  const hoverPos = hover ? positions[hover] : null;

  return (
    <div style={{ position: 'relative', width: '100%', aspectRatio: '1' }}>
      <svg ref={svgRef} viewBox={`${-half} ${-half} ${viewSize} ${viewSize}`}
        style={{ width: '100%', height: '100%' }}
        onMouseMove={handleMouseMove} onMouseUp={handleMouseUp} onMouseLeave={handleMouseUp}>
        {links.map((l, i) => {
          const s = positions[l.source], t = positions[l.target];
          return s && t ? <line key={i} x1={s.x} y1={s.y} x2={t.x} y2={t.y} stroke="var(--map-line, #ccc)" strokeWidth={1} opacity={0.4} /> : null;
        })}
        {nodes.map((n) => {
          const p = positions[n.id]; if (!p) return null;
          const r = Math.sqrt((n.violations || 0) + 1) * 4 + 4;
          return (
            <g key={n.id} transform={`translate(${p.x},${p.y})`} style={{ cursor: n.isFile ? 'default' : 'pointer' }}
              onMouseDown={(e) => handleMouseDown(e, n.id)} onClick={() => handleClick(n)}
              onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover(null)}>
              <circle r={r} fill={nodeColor(n, viewMode)}
                stroke={n.isFile ? 'none' : 'var(--map-folder-stroke, #555)'} strokeWidth={n.isFile ? 0 : 2} />
              {(n.violations || 0) >= 3 && <text textAnchor="middle" dy={r + 12} fontSize={10} fill="currentColor">{n.name}</text>}
            </g>
          );
        })}
      </svg>
      {hoverNode && hoverPos && (
        <div className="map-tooltip" style={{ position: 'absolute', left: '50%', top: 8, pointerEvents: 'none' }}>
          <div className="map-tooltip-title">{hoverNode.path || hoverNode.name}</div>
          <div className="map-tooltip-row"><span>Violations</span><span>{hoverNode.violations}</span></div>
          <div className="map-tooltip-row"><span>Compliance</span><span>{hoverNode.compliance}</span></div>
          <div className="map-tooltip-row"><span>Rate</span><span>{Math.round((hoverNode.complianceRate || 0) * 100)}%</span></div>
        </div>
      )}
    </div>
  );
}
