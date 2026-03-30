import { memo } from 'react';
import { buildSingleViolationPlanText } from '../../../utils/planBuilder.js';
import { buildFilePlanText } from '../../../utils/planTextBuilders.js';
import { SEVERITY_ORDER, parseFileRef } from '../../../utils/formatters.js';
import CopyButton from '../../../components/CopyButton.jsx';
import FileCopyBtn from '../../../components/FileCopyBtn.jsx';
import ContextBlock from '../../../components/ContextBlock.jsx';
import { copyToClipboard } from '../../../utils/clipboard.js';

const ANIM_DELAY_PER_ITEM_MS = 30;
const ANIM_MAX_DELAY_MS = 300;

function buildViolationPlanText(v) {
  const title = [v.dimension, v.principle].filter(Boolean).join(' / ') || 'Violation';
  return buildSingleViolationPlanText(v, title);
}

function ViolationCard({ v, index }) {
  const { filePath, line } = parseFileRef(v.file, v.line);
  const filename = filePath ? filePath.split('/').pop() : null;
  const ref = line != null ? `${filePath}:${line}` : filePath;
  const display = line != null ? `${filename}:${line}` : filename;
  return (
    <div className={`vdetail-row vdetail-row--${v.severity}`} style={{ animationDelay: `${Math.min(index * ANIM_DELAY_PER_ITEM_MS, ANIM_MAX_DELAY_MS)}ms` }}>
      <div className="vdetail-row-main">
        <span className={`severity-tag ${v.severity}`}>{v.severity}</span>
        {v.dimension && <span className="vrow-label">[{v.dimension}]</span>}
        {v.principle && <span className="vrow-label">[{v.principle}]</span>}
        {filename && (
          <FileCopyBtn display={display} copyText={ref} />
        )}
        <CopyButton
          label="Fix plan"
          onClick={() => copyToClipboard(buildViolationPlanText(v))}
        />
      </div>
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
        <ContextBlock context={v.context} snippet={v.snippet} />
      </div>
    </div>
  );
}

function FileSeverityStats({ file, totalViolations, dimensionsCount }) {
  return (
    <div className="file-detail-stats">
      {file.critical > 0 && (
        <span className="file-detail-stat severity-tag critical">{file.critical} critical</span>
      )}
      {file.major > 0 && (
        <span className="file-detail-stat severity-tag major">{file.major} major</span>
      )}
      {file.minor > 0 && (
        <span className="file-detail-stat severity-tag minor">{file.minor} minor</span>
      )}
      {(file.critical > 0 || file.major > 0 || file.minor > 0) && <span className="file-detail-stat-sep">·</span>}
      <span className="file-detail-stat">
        <strong>{totalViolations}</strong> violations
      </span>
      <span className="file-detail-stat-sep">·</span>
      <span className="file-detail-stat">
        <strong>{dimensionsCount}</strong> {dimensionsCount === 1 ? 'dimension' : 'dimensions'}
      </span>
    </div>
  );
}

function SeverityGroup({ sev, violations }) {
  if (violations.length === 0) return null;
  return (
    <div>
      <div className="violation-group-header">
        <span className="violation-group-title">{sev.charAt(0).toUpperCase() + sev.slice(1)}</span>
        <span className="violation-group-count">{violations.length}</span>
      </div>
      <div className="vlive-violations-group">
        {violations.map((v, idx) => (
          <ViolationCard key={idx} v={v} index={idx} />
        ))}
      </div>
    </div>
  );
}

const FileDetailPage = memo(function FileDetailPage({ file }) {
  const totalViolations = file.total || 0;
  const dimensionsCount = file.dimensionsCount || 0;

  return (
    <>
      <section className="panel file-detail-summary-panel">
        <h3 className="file-detail-title">{file.file}</h3>
        <div className="file-detail-stats-row">
          <FileSeverityStats file={file} totalViolations={totalViolations} dimensionsCount={dimensionsCount} />
          <CopyButton
            label="File fix plan"
            onClick={() => copyToClipboard(buildFilePlanText(file))}
          />
        </div>
      </section>

      {SEVERITY_ORDER.map((sev) => (
        <SeverityGroup key={sev} sev={sev} violations={file.violationsBySeverity?.[sev] || []} />
      ))}
    </>
  );
});

export default FileDetailPage;
