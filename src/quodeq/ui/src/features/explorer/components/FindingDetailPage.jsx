/**
 * FindingDetailPage — renders a single violation card in isolation.
 *
 * Used when the user clicks a row in the overview's TOP_FINDINGS table: they
 * land on a page showing just that one EvalViolationCard (with its REASON /
 * DETAIL / code block) plus a terminal-style header for context.
 *
 * This is a lean view — no grouping, no filter pills, no full principle
 * summary. If the user wants the principle's full list, there's already the
 * PrincipleDetailPage route.
 */
import { TermHeader, SevBadge, SectionLabel } from '../../../components/terminal/index.js';
import { EvalViolationCard } from './EvalCards.jsx';
import { t } from '../../../strings/index.js';

export default function FindingDetailPage({ finding, principle, dimension, onDismiss }) {
  if (!finding) {
    return (
      <section className="empty-state">
        <h2>{t('explorer.noFindingSelected')}</h2>
      </section>
    );
  }

  const severity = (finding.severity || 'minor').toLowerCase();
  const shortSev = severity.toUpperCase().slice(0, 4);

  return (
    <section className="finding-detail-page">
      <TermHeader
        name={`${principle || dimension || t('explorer.findingFallback')}.detail`}
        sub={
          <span className="finding-detail-breadcrumb">
            <span>{t('explorer.overviewCrumb')}</span>
            {dimension && <> <span className="finding-detail-sep">▸</span> <span>{String(dimension).toLowerCase()}</span></>}
            {principle && <> <span className="finding-detail-sep">▸</span> <span>{String(principle).toLowerCase()}</span></>}
          </span>
        }
      />

      <SectionLabel>{t('explorer.sevCount', { severity: shortSev, count: 1 })}</SectionLabel>

      <div className="vlive-violations-group">
        <EvalViolationCard
          v={finding}
          principle={principle || finding.principle}
          index={0}
          onDismiss={onDismiss}
        />
      </div>
    </section>
  );
}
