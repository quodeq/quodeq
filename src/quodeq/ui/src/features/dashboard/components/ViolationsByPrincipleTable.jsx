// Props: { violations, onPrincipleClick, pageSize = 20 }
// Groups violations by principle, shows count and severity breakdown.
// Has pagination. onPrincipleClick is called with the grouped principle object when clicked.

import { memo, useMemo, useState } from 'react';

function PrincipleRow({ p, idx, onPrincipleClick }) {
  return (
    <li
      key={p.principle || idx}
      className={`offending-file-row${onPrincipleClick ? ' offending-file-row--clickable' : ''}`}
      role={onPrincipleClick ? 'button' : undefined}
      tabIndex={onPrincipleClick ? 0 : undefined}
      onClick={onPrincipleClick ? () => onPrincipleClick(p) : undefined}
      onKeyDown={onPrincipleClick ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onPrincipleClick(p); } } : undefined}
    >
      <div className="offending-file-info">
        <span className="offending-file-path">{p.principle}</span>
        {p.dimensionsStr && (
          <span className="offending-file-dims">{p.dimensionsStr}</span>
        )}
      </div>
      <strong className="offending-file-total">{p.total}</strong>
      <span className="offending-file-tags">
        {p.critical > 0 && <span className="severity-tag critical">{p.critical} critical</span>}
        {p.major > 0 && <span className="severity-tag major">{p.major} major</span>}
        {p.minor > 0 && <span className="severity-tag minor">{p.minor} minor</span>}
      </span>
      {onPrincipleClick && <span className="offending-file-chevron">›</span>}
    </li>
  );
}

function groupViolationsByPrinciple(violations) {
  const bucket = new Map();
  violations.forEach(v => {
    const name = v.principle || '(unknown)';
    const sev = (v.severity || 'minor').toLowerCase();
    const cur = bucket.get(name) || {
      principle: name,
      total: 0,
      critical: 0,
      major: 0,
      minor: 0,
      violations: [],
      dimensions: new Set(),
    };
    cur.total++;
    if (cur[sev] !== undefined) cur[sev]++;
    cur.violations.push(v);
    if (v.dimension) cur.dimensions.add(v.dimension);
    bucket.set(name, cur);
  });
  return Array.from(bucket.values()).map(p => ({
    ...p,
    dimensionsStr: p.dimensions.size > 0 ? Array.from(p.dimensions).sort().join(', ') : '',
  })).sort((a, b) => {
    if (b.critical !== a.critical) return b.critical - a.critical;
    if (b.major !== a.major) return b.major - a.major;
    return b.minor - a.minor;
  });
}

const ViolationsByPrincipleTable = memo(function ViolationsByPrincipleTable({ violations, onPrincipleClick, pageSize = 20 }) {
  const [showAll, setShowAll] = useState(false);

  const grouped = useMemo(() => groupViolationsByPrinciple(violations), [violations]);

  const displayItems = showAll ? grouped : grouped.slice(0, pageSize);
  const hasMore = grouped.length > pageSize;

  return (
    <>
      <ul className="offending-file-list">
        {displayItems.map((p, idx) => (
          <PrincipleRow key={p.principle || idx} p={p} idx={idx} onPrincipleClick={onPrincipleClick} />
        ))}
      </ul>
      {hasMore && (
        <button className="offending-show-more" onClick={() => setShowAll(v => !v)}>
          {showAll ? 'Show less' : `Show all ${grouped.length} principles`}
        </button>
      )}
    </>
  );
});

export default ViolationsByPrincipleTable;
