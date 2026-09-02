import { memo } from 'react';
import { SparkleIcon } from '../../../components/CopyButton.jsx';
import FileCopyBtn from '../../../components/FileCopyBtn.jsx';
import ContextBlock from '../../../components/ContextBlock.jsx';
import { useSidePane, violationFixPlanSpec } from '../../side-pane/index.js';
import { VerifiedChip } from '../../violations/components/VerifiedChip.jsx';
import { parseFileRef } from '../../../utils/formatters.js';
import { t } from '../../../strings/index.js';
import { severityLabel, scopeGateRuleLabel } from '../../../strings/labels.js';

/** The reason/detail body: title, reason text, linked references, and the
 * file context block. */
function ViolationCardDetail({ v }) {
  const linkedRefs = v.reqRefs?.filter(r => r.url && /^https?:\/\//.test(r.url)) || [];
  return (
    <div className="vlive-detail">
      {(v.title || v.reason) && (
        <div className="vlive-detail-section">
          <div className="vlive-detail-section-header">
            <span className="vlive-detail-section-label">{t('violations.reasonLabel')}</span>
            {linkedRefs.length > 0 &&
              <span className="cwe-link-group">{linkedRefs.map((ref, i) => (
                <a key={i} className="cwe-link" href={ref.url} target="_blank" rel="noopener noreferrer">{ref.label}</a>
              ))}</span>
            }
          </div>
          {v.title && <p className="vlive-detail-title">{v.title}</p>}
          {v.reason && <>
            <span className="vlive-detail-section-label">{t('violations.detailLabel')}</span>
            <p className="vlive-detail-reason">{v.reason}</p>
          </>}
        </div>
      )}
      <ContextBlock context={v.context} snippet={v.snippet} scope={v.scope} line={v.line} endLine={v.endLine} />
    </div>
  );
}

/** The verified chip, fix-plan trigger, and (when a handler is given) the
 * dismiss control. */
function ViolationCardActions({ v, onDismiss }) {
  const { addWindow } = useSidePane();
  return (
    <div className="vrow-actions">
      <VerifiedChip v={v} />
      <button
        type="button"
        className="fix-plan-btn"
        onClick={() => { const spec = violationFixPlanSpec(v); if (spec) addWindow(spec); }}
      >
        <SparkleIcon />
        {t('explorer.fixPlan')}
      </button>
      {onDismiss && (
        <button
          type="button"
          className="dismiss-btn"
          onClick={(e) => { e.stopPropagation(); onDismiss(v); }}
          title={t('explorer.dismissFinding')}
          aria-label={t('explorer.dismissFinding')}
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
        </button>
      )}
    </div>
  );
}

function ViolationCardMarkup({ v, filename, display, refText, onDismiss }) {
  return (
    <div className={`vdetail-row vdetail-row--${v.severity}`}>
      <div className="vdetail-row-main">
        <span className={`severity-tag ${v.severity}`}>{severityLabel(v.severity)}</span>
        {v.provenanceDowngrade && (
          <span
            className="provenance-downgrade-tag"
            title={t('explorer.provenanceDowngradeTitle')}
          >
            {t('explorer.downgradedFromCritical')}
          </span>
        )}
        {v.scopeDowngrade && (
          <span
            className="scope-downgrade-tag"
            title={t('explorer.scopeDowngradeTitle')}
          >
            {t('explorer.scopeDowngradeBadge', { rule: scopeGateRuleLabel(v.scopeDowngrade.rule) })}
          </span>
        )}
        {v.dimension && <span className="vrow-label">[{v.dimension}]</span>}
        {v.principle && <span className="vrow-label">[{v.principle}]</span>}
        {filename && (
          <FileCopyBtn display={display} copyText={refText} />
        )}
        <ViolationCardActions v={v} onDismiss={onDismiss} />
      </div>
      <ViolationCardDetail v={v} />
    </div>
  );
}

const ViolationCard = memo(function ViolationCard({ v, onDismiss }) {
  const { filePath, line } = parseFileRef(v.file, v.line);
  const filename = filePath ? filePath.split('/').pop() : null;
  const range = (v.endLine && v.endLine !== line) ? `${line}-${v.endLine}` : line;
  const refText = line != null ? `${filePath}:${range}` : filePath;
  const display = line != null ? `${filename}:${range}` : filename;
  return <ViolationCardMarkup v={v} filename={filename} display={display} refText={refText} onDismiss={onDismiss} />;
});

export default ViolationCard;
