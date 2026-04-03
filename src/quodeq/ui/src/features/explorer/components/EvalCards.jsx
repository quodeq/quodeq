import { parseFileRef } from '../../../utils/formatters.js';
import CopyButton, { SparkleIcon } from '../../../components/CopyButton.jsx';
import FileCopyBtn from '../../../components/FileCopyBtn.jsx';
import ContextBlock from '../../../components/ContextBlock.jsx';
import { copyToClipboard } from '../../../utils/clipboard.js';

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
  return (
    <div className="vlive-detail">
      {(item.title || item.reason || item.findings) && (
        <div className="vlive-detail-section">
          <div className="vlive-detail-section-header">
            {item.title && <span className="vlive-detail-section-label">Reason</span>}
            <RefsLinks reqRefs={item.reqRefs} />
          </div>
          {item.title && <p className="vlive-detail-title">{item.title}</p>}
          {item.reason && <>
            <span className="vlive-detail-section-label">Detail</span>
            <p className="vlive-detail-reason">{item.reason}</p>
          </>}
        </div>
      )}
      <ContextBlock context={item.context} snippet={item.snippet} scope={item.scope} line={item.line} endLine={item.endLine} />
    </div>
  );
}

export function EvalViolationCard({ v, principle, buildViolationPlanText, index, onDismiss }) {
  const { filename, ref, display } = useFileInfo(v.file, v.line, v.endLine);
  return (
    <div className={`vdetail-row vdetail-row--${v.severity}`} style={{ animationDelay: `${Math.min(index * ANIM_DELAY_PER_ITEM_MS, ANIM_MAX_DELAY_MS)}ms` }}>
      <div className="vdetail-row-main">
        <span className={`severity-tag ${v.severity}`}>{v.severity}</span>
        <span className="vrow-label">[{v.principle || principle}]</span>
        {filename && <FileCopyBtn display={display} copyText={ref} />}
        <CopyButton
          label="Fix plan"
          className="fix-plan-btn"
          icon={<SparkleIcon />}
          onClick={() => copyToClipboard(buildViolationPlanText(v))}
        />
        {onDismiss && (
          <button
            type="button"
            className="dismiss-btn"
            onClick={(e) => { e.stopPropagation(); onDismiss(v); }}
            title="Dismiss this finding (exclude from scoring)"
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
    <div className="vdetail-row vdetail-row--compliant" style={{ animationDelay: `${Math.min(index * ANIM_DELAY_PER_ITEM_MS, ANIM_MAX_DELAY_MS)}ms` }}>
      <div className="vdetail-row-main">
        <span className="severity-tag compliance">compliant</span>
        <span className="vrow-label">[{c.principle || principle}]</span>
        {filename && <FileCopyBtn display={display} copyText={ref} />}
      </div>
      <ViolationDetail item={c} />
    </div>
  );
}
