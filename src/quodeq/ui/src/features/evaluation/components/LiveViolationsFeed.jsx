import { useState, useMemo } from 'react';
import FileCopyBtn from '../../../components/FileCopyBtn.jsx';
import ContextBlock from '../../../components/ContextBlock.jsx';
import { parseFileRef } from '../../../utils/formatters.js';

const ANIM_DELAY_PER_ITEM_MS = 40;
const ANIM_MAX_DELAY_MS = 400;

function severityOrder(s) {
  return s === 'critical' ? 0 : s === 'major' ? 1 : 2;
}

function ViolationLiveRow({ violation, index }) {
  const [open, setOpen] = useState(false);
  const v = violation;
  const { filePath, line } = parseFileRef(v.file, v.line);
  const filename = filePath ? filePath.split('/').pop() : null;
  const range = (v.endLine && v.endLine !== line) ? `${line}-${v.endLine}` : line;
  const ref = line != null ? `${filePath}:${range}` : filePath;
  const display = line != null ? `${filename}:${range}` : filename;

  return (
    <div
      className={`vdetail-row vdetail-row--${v.severity}`}
      style={{ animationDelay: `${Math.min(index * ANIM_DELAY_PER_ITEM_MS, ANIM_MAX_DELAY_MS)}ms` }}
    >
      <div
        className="vdetail-row-main vlive-collapsible"
        role="button"
        tabIndex={0}
        aria-expanded={open}
        aria-label={`${v.severity} finding: ${v.title || v.file || 'details'}`}
        onClick={() => setOpen(o => !o)}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setOpen(o => !o); } }}
      >
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
                {v.reqRefs?.filter(r => r.url && /^https?:\/\//.test(r.url))?.length > 0 &&
                  <span className="cwe-link-group">{v.reqRefs.filter(r => r.url && /^https?:\/\//.test(r.url)).map((ref, i) => (
                    <a key={i} className="cwe-link" href={ref.url} target="_blank" rel="noopener noreferrer">{ref.label}</a>
                  ))}</span>
                }
              </div>
              {v.title && <p className="vlive-detail-title">{v.title}</p>}
              {v.reason && <>
                <span className="vlive-detail-section-label">Detail</span>
                <p className="vlive-detail-reason">{v.reason}</p>
              </>}
            </div>
          )}
          <ContextBlock context={v.context} snippet={v.snippet} scope={v.scope} line={v.line} endLine={v.endLine} />
        </div>
      )}
    </div>
  );
}

export default function LiveViolationsFeed({ liveViolations }) {
  const dims = Object.keys(liveViolations ?? {});
  const totalCount = dims.reduce((sum, d) => sum + (liveViolations[d]?.length ?? 0), 0);

  const sortedByDim = useMemo(() => {
    const result = {};
    for (const dim of Object.keys(liveViolations ?? {})) {
      result[dim] = [...(liveViolations[dim] ?? [])].sort((a, b) =>
        severityOrder(a.severity) - severityOrder(b.severity)
      );
    }
    return result;
  }, [liveViolations]);

  if (!totalCount) return null;

  return (
    <div className="vlive-feed">
      <div className="vlive-counter">
        {totalCount} violation{totalCount !== 1 ? 's' : ''} found across {dims.length} dimension{dims.length !== 1 ? 's' : ''}
      </div>
      {dims.map(dim => {
        const violations = sortedByDim[dim] || [];
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
