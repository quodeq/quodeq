import { parseFileRef } from '../../../utils/formatters.js';
import CopyButton from '../../../components/CopyButton.jsx';
import FileCopyBtn from '../../../components/FileCopyBtn.jsx';
import ContextBlock from '../../../components/ContextBlock.jsx';
import { copyToClipboard } from '../../../utils/clipboard.js';

const ANIM_DELAY_PER_ITEM_MS = 30;
const ANIM_MAX_DELAY_MS = 300;

function filterValidRefs(refs) {
  return (refs || []).filter((r) => r.url && /^https?:\/\//.test(r.url));
}

function useFileInfo(file, fileLine) {
  const { filePath, line } = parseFileRef(file, fileLine);
  const filename = filePath ? filePath.split('/').pop() : null;
  const ref = line != null ? `${filePath}:${line}` : filePath;
  const display = line != null ? `${filename}:${line}` : filename;
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

export function EvalViolationCard({ v, principle, buildViolationPlanText, index }) {
  const { filename, ref, display } = useFileInfo(v.file, v.line);
  return (
    <div className={`vdetail-row vdetail-row--${v.severity}`} style={{ animationDelay: `${Math.min(index * ANIM_DELAY_PER_ITEM_MS, ANIM_MAX_DELAY_MS)}ms` }}>
      <div className="vdetail-row-main">
        <span className={`severity-tag ${v.severity}`}>{v.severity}</span>
        <span className="vrow-label">[{v.principle || principle}]</span>
        {filename && <FileCopyBtn display={display} copyText={ref} />}
        <CopyButton label="Fix plan" onClick={() => copyToClipboard(buildViolationPlanText(v))} />
      </div>
      <div className="vlive-detail">
        {(v.title || v.reason || v.findings) && (
          <div className="vlive-detail-section">
            <div className="vlive-detail-section-header">
              {v.title && <span className="vlive-detail-section-label">Reason</span>}
              <RefsLinks reqRefs={v.reqRefs} />
            </div>
            {v.title && <p className="vlive-detail-title">{v.title}</p>}
            {v.reason && <>
              <span className="vlive-detail-section-label">Detail</span>
              <p className="vlive-detail-reason">{v.reason}</p>
            </>}
          </div>
        )}
        <ContextBlock context={v.context} snippet={v.snippet} scope={v.scope} />
      </div>
    </div>
  );
}

export function ComplianceCard({ c, principle, index }) {
  const { filename, ref, display } = useFileInfo(c.file, c.line);
  return (
    <div className="vdetail-row vdetail-row--compliant" style={{ animationDelay: `${Math.min(index * ANIM_DELAY_PER_ITEM_MS, ANIM_MAX_DELAY_MS)}ms` }}>
      <div className="vdetail-row-main">
        <span className="severity-tag compliance">compliant</span>
        <span className="vrow-label">[{c.principle || principle}]</span>
        {filename && <FileCopyBtn display={display} copyText={ref} />}
      </div>
      <div className="vlive-detail">
        {(c.title || c.reason) && (
          <div className="vlive-detail-section">
            <div className="vlive-detail-section-header">
              {c.title && <span className="vlive-detail-section-label">Reason</span>}
              <RefsLinks reqRefs={c.reqRefs} />
            </div>
            {c.title && <p className="vlive-detail-title">{c.title}</p>}
            {c.reason && <>
              <span className="vlive-detail-section-label">Detail</span>
              <p className="vlive-detail-reason">{c.reason}</p>
            </>}
          </div>
        )}
        <ContextBlock context={c.context} snippet={c.snippet} scope={c.scope} />
      </div>
    </div>
  );
}
