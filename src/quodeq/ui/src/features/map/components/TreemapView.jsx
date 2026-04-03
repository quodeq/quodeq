import { useMemo } from 'react';
import { Treemap, ResponsiveContainer, Tooltip } from 'recharts';
import { worstSeverity, severityColor, complianceRateColor, nodeSize } from '../utils/mapColors.js';

function MapTooltipContent({ active, payload }) {
  if (!active || !payload || !payload.length) return null;
  const node = payload[0]?.payload;
  if (!node) return null;
  const total = node.violations + node.compliance;
  const rate = total > 0 ? ((node.compliance / total) * 100).toFixed(0) : '—';
  return (
    <div className="map-tooltip">
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

function CustomTreemapContent(props) {
  const { x, y, width, height, name, viewMode, severity, complianceRate, violations, compliance } = props;
  if (width < 4 || height < 4) return null;

  const sev = worstSeverity(severity || { critical: 0, major: 0, minor: 0 });
  const fill = viewMode === 'violations' ? severityColor(sev) : complianceRateColor(complianceRate || 0);

  const showLabel = width > 40 && height > 20;
  const showCount = width > 60 && height > 35;

  return (
    <g>
      <rect x={x} y={y} width={width} height={height} rx={3} style={{ fill, stroke: 'var(--color-bg)', strokeWidth: 2, cursor: 'pointer', opacity: 0.85 }} />
      {showLabel && (
        <text x={x + width / 2} y={y + height / 2 - (showCount ? 6 : 0)} textAnchor="middle" dominantBaseline="central" style={{ fontSize: Math.min(12, width / 8), fill: '#fff', fontWeight: 600, pointerEvents: 'none' }}>
          {name.length > width / 7 ? name.slice(0, Math.floor(width / 7)) + '…' : name}
        </text>
      )}
      {showCount && (
        <text x={x + width / 2} y={y + height / 2 + 10} textAnchor="middle" dominantBaseline="central" style={{ fontSize: 10, fill: 'rgba(255,255,255,0.8)', pointerEvents: 'none' }}>
          {violations}v · {compliance}c
        </text>
      )}
    </g>
  );
}

export default function TreemapView({ node, viewMode, onDrillDown, containerHeight }) {
  const treemapData = useMemo(() => {
    const toEntry = (n) => ({
      name: n.name,
      path: n.path,
      isFile: n.isFile,
      size: nodeSize(n, viewMode),
      violations: n.violations,
      compliance: n.compliance,
      complianceRate: n.complianceRate,
      severity: n.severity,
      dimensions: n.dimensions,
      // preserve children ref for drill-down check, but as a non-recharts key
      _children: n.children,
    });
    if (!node || !node.children || node.children.length === 0) {
      return [toEntry(node)];
    }
    return node.children.map(toEntry);
  }, [node, viewMode]);

  const handleClick = (entry) => {
    if (entry && !entry.isFile && entry._children && entry._children.length > 0) {
      onDrillDown(entry.path);
    }
  };

  return (
    <ResponsiveContainer width="100%" height={containerHeight || 400}>
      <Treemap
        data={treemapData}
        dataKey="size"
        stroke="var(--color-bg)"
        onClick={handleClick}
        content={<CustomTreemapContent viewMode={viewMode} />}
        isAnimationActive={false}
      >
        <Tooltip content={<MapTooltipContent />} />
      </Treemap>
    </ResponsiveContainer>
  );
}
