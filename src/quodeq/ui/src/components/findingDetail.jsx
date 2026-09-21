/**
 * The parts of a finding's presentation that every list of findings shares:
 * its linked requirement references and its REASON / DETAIL / context body.
 *
 * Explorer's violation cards, the live evaluation feed and the dismissed
 * sub-tab all render these, so they live in the shared component layer rather
 * than in any one feature.
 */
import ContextBlock from './ContextBlock.jsx';
import { filterValidRefs } from '../utils/reqRefs.js';
import { t } from '../strings/index.js';

/**
 * The linked requirement references beside a finding's REASON label, or
 * nothing when none of them carries a web link.
 */
export function RefLinks({ reqRefs }) {
  const valid = filterValidRefs(reqRefs);
  if (valid.length === 0) return null;
  return (
    <span className="cwe-link-group">
      {valid.map((r, i) => (
        <a key={i} className="cwe-link" href={r.url} target="_blank" rel="noopener noreferrer">{r.label}</a>
      ))}
    </span>
  );
}

/**
 * A finding's expanded body: its title under a REASON label, its reason text
 * under a DETAIL label, and the source context underneath. The whole reason
 * section is dropped for a finding that carries neither.
 */
export function FindingDetailBody({ v }) {
  return (
    <div className="vlive-detail">
      {(v.title || v.reason) && (
        <div className="vlive-detail-section">
          <div className="vlive-detail-section-header">
            <span className="vlive-detail-section-label">{t('violations.reasonLabel')}</span>
            <RefLinks reqRefs={v.reqRefs} />
          </div>
          {v.title && <p className="vlive-detail-title">{v.title}</p>}
          {v.reason && <>
            <span className="vlive-detail-section-label">{t('violations.detailLabel')}</span>
            <p className="vlive-detail-reason">{v.reason}</p>
          </>}
        </div>
      )}
      <ContextBlock context={v.context} snippet={v.snippet} scope={v.scope} line={v.line} />
    </div>
  );
}
