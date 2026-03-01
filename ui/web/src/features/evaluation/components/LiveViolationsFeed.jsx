import { useState } from 'react';

function severityOrder(s) {
  return s === 'critical' ? 0 : s === 'major' ? 1 : 2;
}

function ViolationLiveRow({ violation, index }) {
  const [open, setOpen] = useState(false);

  return (
    <div
      className={`vlive-row vlive-row--${violation.severity}`}
      style={{ animationDelay: `${Math.min(index * 40, 400)}ms` }}
    >
      <div className="vlive-row-main" onClick={() => setOpen(o => !o)}>
        <span className={`severity-tag ${violation.severity}`}>{violation.severity}</span>
        <span className="vlive-principle">{violation.principle}</span>
        <span className="vlive-file">{violation.file?.split('/').pop() ?? violation.file}</span>
        <svg
          className={`vlive-chevron${open ? ' open' : ''}`}
          width="14" height="14" viewBox="0 0 24 24"
          fill="none" stroke="currentColor" strokeWidth="2.5"
          strokeLinecap="round" strokeLinejoin="round"
        >
          <polyline points="9 18 15 12 9 6" />
        </svg>
      </div>
      {open && (
        <div className="vlive-detail">
          <div className="vlive-detail-row">
            <span className="vlive-detail-label">File</span>
            <code className="vlive-detail-value">{violation.file}</code>
          </div>
          {violation.line != null && (
            <div className="vlive-detail-row">
              <span className="vlive-detail-label">Line</span>
              <code className="vlive-detail-value">{violation.line}</code>
            </div>
          )}
          {violation.reason && (
            <div className="vlive-detail-row">
              <span className="vlive-detail-label">Reason</span>
              <span className="vlive-detail-value vlive-detail-value--prose">{violation.reason}</span>
            </div>
          )}
          {violation.snippet && (
            <pre className="vlive-snippet">{violation.snippet}</pre>
          )}
        </div>
      )}
    </div>
  );
}

export default function LiveViolationsFeed({ liveViolations }) {
  const dims = Object.keys(liveViolations ?? {});
  if (!dims.length) return null;

  const totalCount = dims.reduce((sum, d) => sum + (liveViolations[d]?.length ?? 0), 0);

  return (
    <div className="vlive-feed">
      <div className="vlive-counter">
        {totalCount} violation{totalCount !== 1 ? 's' : ''} found across {dims.length} dimension{dims.length !== 1 ? 's' : ''}
      </div>
      {dims.map(dim => {
        const violations = [...(liveViolations[dim] ?? [])].sort((a, b) =>
          severityOrder(a.severity) - severityOrder(b.severity)
        );
        return (
          <div key={dim} className="vlive-dimension-group">
            <div className="vlive-dimension-label">{dim}</div>
            {violations.map((v, i) => (
              <ViolationLiveRow key={`${dim}-${i}`} violation={v} index={i} />
            ))}
          </div>
        );
      })}
    </div>
  );
}
