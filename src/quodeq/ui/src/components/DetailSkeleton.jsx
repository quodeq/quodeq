import { t } from '../strings/index.js';

/**
 * Stands in for a finding's DETAIL text and code while the page's detail
 * query answers (api/complianceDetail.js). House skeleton idiom: static
 * dimmed blocks, no shimmer, no spinner.
 */
export default function DetailSkeleton() {
  return (
    <div className="detail-skeleton" role="status" aria-busy="true" aria-label={t('explorer.detailLoading')}>
      <span className="detail-skeleton__bar detail-skeleton__bar--line" />
      <span className="detail-skeleton__bar detail-skeleton__bar--line detail-skeleton__bar--short" />
      <span className="detail-skeleton__bar detail-skeleton__bar--code" />
    </div>
  );
}
