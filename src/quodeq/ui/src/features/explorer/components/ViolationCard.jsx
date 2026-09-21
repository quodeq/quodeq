import { memo } from 'react';
import FileCopyBtn from '../../../components/FileCopyBtn.jsx';
import { FindingDetailBody } from '../../../components/findingDetail.jsx';
import { ViolationActions } from './violationActions.jsx';
import { parseFileRef } from '../../../utils/formatters.js';
import { t } from '../../../strings/index.js';
import { severityLabel, scopeGateRuleLabel } from '../../../strings/labels.js';

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
        <ViolationActions v={v} onDismiss={onDismiss} />
      </div>
      <FindingDetailBody v={v} />
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
