import { parseFileRef } from '../../../utils/formatters.js';
import CopyButton from '../../../components/CopyButton.jsx';
import FileCopyBtn from '../../../components/FileCopyBtn.jsx';
import { copyToClipboard } from '../../../utils/clipboard.js';

const ANIM_DELAY_PER_ITEM_MS = 30;
const ANIM_MAX_DELAY_MS = 300;

function filterValidRefs(refs) {
  return (refs || []).filter((r) => r.url && /^https?:\/\//.test(r.url));
}

export function EvalViolationCard({ v, principle, buildViolationPlanText, index }) {
  const { filePath, line } = parseFileRef(v.file, v.line);
  const filename = filePath ? filePath.split('/').pop() : null;
  const ref = line != null ? `${filePath}:${line}` : filePath;
  const display = line != null ? `${filename}:${line}` : filename;
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
              {filterValidRefs(v.reqRefs).length > 0 &&
                <span className="cwe-link-group">{filterValidRefs(v.reqRefs).map((ref, i) => (
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
        {v.snippet && <pre className="vlive-snippet">{v.snippet.replace(/\\n/g, '\n')}</pre>}
      </div>
    </div>
  );
}

export function ComplianceCard({ c, principle, index }) {
  const { filePath, line } = parseFileRef(c.file, c.line);
  const filename = filePath ? filePath.split('/').pop() : null;
  const ref = line != null ? `${filePath}:${line}` : filePath;
  const display = line != null ? `${filename}:${line}` : filename;
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
              {filterValidRefs(c.reqRefs).length > 0 &&
                <span className="cwe-link-group">{filterValidRefs(c.reqRefs).map((ref, i) => (
                  <a key={i} className="cwe-link" href={ref.url} target="_blank" rel="noopener noreferrer">{ref.label}</a>
                ))}</span>
              }
            </div>
            {c.title && <p className="vlive-detail-title">{c.title}</p>}
            {c.reason && <>
              <span className="vlive-detail-section-label">Detail</span>
              <p className="vlive-detail-reason">{c.reason}</p>
            </>}
          </div>
        )}
        {c.snippet && <pre className="vlive-snippet">{c.snippet.replace(/\\n/g, '\n')}</pre>}
      </div>
    </div>
  );
}
