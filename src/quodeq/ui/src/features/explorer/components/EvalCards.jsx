import { useRef } from 'react';
import { parseFileRef } from '../../../utils/formatters.js';
import { SparkleIcon } from '../../../components/CopyButton.jsx';
import FileCopyBtn from '../../../components/FileCopyBtn.jsx';
import ContextBlock from '../../../components/ContextBlock.jsx';
import SevBadge from '../../../components/terminal/SevBadge.jsx';
import usePretextHeight from '../../../hooks/usePretextHeight.js';
import { useSidePane, violationFixPlanSpec } from '../../side-pane/index.js';
import { useVerifiedFindings } from '../../violations/components/verifiedFindingsContext.jsx';

const ANIM_DELAY_PER_ITEM_MS = 30;
const ANIM_MAX_DELAY_MS = 300;

function filterValidRefs(refs) {
  return (refs || []).filter((r) => r.url && /^https?:\/\//.test(r.url));
}

function useFileInfo(file, fileLine, fileEndLine) {
  const { filePath, line } = parseFileRef(file, fileLine);
  const filename = filePath ? filePath.split('/').pop() : null;
  const range = (fileEndLine && fileEndLine !== line) ? `${line}-${fileEndLine}` : line;
  const ref = line != null ? `${filePath}:${range}` : filePath;
  const display = line != null ? `${filename}:${range}` : filename;
  return { filePath, filename, ref, display };
}

function RefsLinks({ reqRefs }) {
  const valid = filterValidRefs(reqRefs);
  if (valid.length === 0) return null;
  return (
    <span className="cwe-link-group">{valid.map((r, i) => (
      <a key={i} className="cwe-link" href={r.url} target="_blank" rel="noopener noreferrer">{r.label}</a>
    ))}</span>
  );
}

function ViolationDetail({ item }) {
  // Measure the wrap-sensitive REASON title and DETAIL paragraph off-DOM via
  // pretext so heights are stable across resizes and so a future virtualiser
  // can query them without paint. The measured paragraph is set as
  // `min-height` on the element to reserve space before layout.
  const titleRef = useRef(null);
  const reasonRef = useRef(null);
  const titleMeasure = usePretextHeight(titleRef, item.title, { lineHeight: 18 });
  const reasonMeasure = usePretextHeight(reasonRef, item.reason, { lineHeight: 20 });

  return (
    <div className="vlive-detail vlive-detail--terminal">
      {(item.title || item.reason || item.findings) && (
        <div className="vlive-detail-section">
          <div className="vlive-detail-section-header">
            {item.title && <span className="vlive-detail-section-label">REASON</span>}
            <RefsLinks reqRefs={item.reqRefs} />
          </div>
          {item.title && (
            <p
              ref={titleRef}
              className="vlive-detail-title"
              style={titleMeasure.height ? { minHeight: titleMeasure.height } : undefined}
              data-pretext-lines={titleMeasure.lineCount || undefined}
            >
              {item.title}
            </p>
          )}
          {item.reason && <>
            <span className="vlive-detail-section-label">DETAIL</span>
            <p
              ref={reasonRef}
              className="vlive-detail-reason"
              style={reasonMeasure.height ? { minHeight: reasonMeasure.height } : undefined}
              data-pretext-lines={reasonMeasure.lineCount || undefined}
            >
              {item.reason}
            </p>
          </>}
        </div>
      )}
      <ContextBlock context={item.context} snippet={item.snippet} scope={item.scope} line={item.line} endLine={item.endLine} />
    </div>
  );
}

export function EvalViolationCard({ v, principle, index, onDismiss }) {
  const { addWindow } = useSidePane();
  const { filename, ref, display } = useFileInfo(v.file, v.line, v.endLine);
  const verifiedCtx = useVerifiedFindings();
  const verifiedKey = `${v.req || ''}|${v.file || ''}|${v.line || 0}`;
  const isVerified = Boolean(verifiedCtx?.keys?.has(verifiedKey));
  return (
    <div
      className={`vdetail-row vdetail-row--terminal vdetail-row--${v.severity}`}
      style={{ animationDelay: `${Math.min(index * ANIM_DELAY_PER_ITEM_MS, ANIM_MAX_DELAY_MS)}ms` }}
    >
      <div className="vdetail-row-main">
        <SevBadge level={v.severity} format="long" />
        {isVerified && (
          <button
            type="button"
            className="verified-chip"
            title={`${verifiedCtx.noteFor(verifiedKey) || 'Verified by the assistant'}. Click to remove the badge.`}
            onClick={(e) => { e.stopPropagation(); verifiedCtx.unverify(v); }}
          >
            verified
          </button>
        )}
        <span className="vrow-label">[{v.principle || principle}]</span>
        {filename && <FileCopyBtn display={display} copyText={ref} />}
        <button
          type="button"
          className="fix-plan-btn"
          onClick={() => { const spec = violationFixPlanSpec(v, v.principle || principle); if (spec) addWindow(spec); }}
        >
          <SparkleIcon />
          Fix plan
        </button>
        {onDismiss && (
          <button
            type="button"
            className="dismiss-btn"
            onClick={(e) => { e.stopPropagation(); onDismiss(v); }}
            title="Dismiss this finding (exclude from scoring)"
            aria-label="Dismiss this finding (exclude from scoring)"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          </button>
        )}
      </div>
      <ViolationDetail item={v} />
    </div>
  );
}

export function ComplianceCard({ c, principle, index }) {
  const { filename, ref, display } = useFileInfo(c.file, c.line, c.endLine);
  return (
    <div
      className="vdetail-row vdetail-row--terminal vdetail-row--compliant"
      style={{ animationDelay: `${Math.min(index * ANIM_DELAY_PER_ITEM_MS, ANIM_MAX_DELAY_MS)}ms` }}
    >
      <div className="vdetail-row-main">
        <span className="term-sev-badge term-sev-badge--compliant">COMPLIANT</span>
        <span className="vrow-label">[{c.principle || principle}]</span>
        {filename && <FileCopyBtn display={display} copyText={ref} />}
      </div>
      <ViolationDetail item={c} />
    </div>
  );
}
