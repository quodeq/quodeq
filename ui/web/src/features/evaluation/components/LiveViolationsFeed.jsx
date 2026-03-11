import { useState } from 'react';

function severityOrder(s) {
  return s === 'critical' ? 0 : s === 'major' ? 1 : 2;
}

function CopyIcon() {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <rect x="9" y="9" width="13" height="13" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  );
}

function FileCopyBtn({ display, copyText }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="vlive-detail-file-btn"
      onClick={(e) => {
        e.stopPropagation();
        navigator.clipboard.writeText(copyText);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
    >
      {copied ? 'Copied!' : display}
      <CopyIcon />
    </button>
  );
}

// Parse a raw file string that may or may not carry a trailing :line.
// Returns { filePath, line } where filePath has no line suffix.
function parseFileRef(rawFile, rawLine) {
  if (!rawFile) return { filePath: null, line: rawLine ?? null };
  const m = rawFile.match(/^(.*?)(?::(\d+))?$/);
  const filePath = m[1] || rawFile;
  const line = rawLine ?? (m[2] ? parseInt(m[2], 10) : null);
  return { filePath, line };
}

function ViolationLiveRow({ violation, index }) {
  const [open, setOpen] = useState(false);
  const v = violation;
  const { filePath, line } = parseFileRef(v.file, v.line);
  const filename = filePath ? filePath.split('/').pop() : null;
  const ref = line != null ? `${filePath}:${line}` : filePath;
  const display = line != null ? `${filename}:${line}` : filename;

  return (
    <div
      className={`vdetail-row vdetail-row--${v.severity}`}
      style={{ animationDelay: `${Math.min(index * 40, 400)}ms` }}
    >
      <div className="vdetail-row-main vlive-collapsible" onClick={() => setOpen(o => !o)}>
        <span className={`severity-tag ${v.severity}`}>{v.severity}</span>
        {v.dimension && <span className="vrow-label">[{v.dimension}]</span>}
        {v.principle && <span className="vrow-label">[{v.principle}]</span>}
        {filename && <FileCopyBtn display={display} copyText={ref} />}
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
          {(v.title || v.reason) && (
            <div className="vlive-detail-section">
              <div className="vlive-detail-section-header">
                <span className="vlive-detail-section-label">Reason</span>
                {v.req && <a className="cwe-link" href={v.req_url || '#'} target="_blank" rel="noopener noreferrer">{v.req_label || v.req}</a>}
              </div>
              {v.title && <p className="vlive-detail-title">{v.title}</p>}
              {v.reason && <>
                <span className="vlive-detail-section-label">Detail</span>
                <p className="vlive-detail-reason">{v.reason}</p>
              </>}
            </div>
          )}
          {v.snippet && <pre className="vlive-snippet">{v.snippet}</pre>}
        </div>
      )}
    </div>
  );
}

export default function LiveViolationsFeed({ liveViolations }) {
  const dims = Object.keys(liveViolations ?? {});
  const totalCount = dims.reduce((sum, d) => sum + (liveViolations[d]?.length ?? 0), 0);
  if (!totalCount) return null;

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
              <ViolationLiveRow key={`${dim}-${v.file}-${v.principle}-${String(v.line ?? '')}`} violation={v} index={i} />
            ))}
          </div>
        );
      })}
    </div>
  );
}
