import { useState } from 'react';
import { SectionLabel } from '../../../components/terminal/index.js';
import SevBadge from '../../../components/terminal/SevBadge.jsx';
import TrendBadge from '../../../components/TrendBadge.jsx';
import { scoreColorClass, complianceRatio } from '../../../utils/formatters.js';
import { t, LOCALE } from '../../../strings/index.js';
import ProjectRow from './ProjectRow.jsx';

const nf = (n) => (n == null ? '—' : Number(n).toLocaleString(LOCALE));
const score1 = (s) => (s == null ? '—' : (Math.round(s * 10) / 10).toFixed(1));

function CollapsedUnevaluated({ unevaluated, showUnevaluated, setShowUnevaluated }) {
  return (
    <div className="compare-noevals">
      <button
        type="button"
        className="compare-noevals__toggle"
        aria-expanded={showUnevaluated}
        onClick={() => setShowUnevaluated((v) => !v)}
      >
        <span className="compare-noevals__dot" aria-hidden="true">·</span>
        {t('compare.noEvalsCollapsed', { count: unevaluated.length })}
        <span className="compare-noevals__action">
          {showUnevaluated ? t('compare.hideAction') : t('compare.showAction')} {showUnevaluated ? '▾' : '▸'}
        </span>
      </button>
      {showUnevaluated && unevaluated.map((row) => (
        <div key={row.id} className="compare-noevals__row">
          <span className="compare-row__rank" />
          <span className="compare-row__name">{row.name}</span>
          {row.lang && <span className="compare-row__meta">{row.lang}</span>}
          <span className="compare-noevals__note">{t('compare.noRuns')}</span>
        </div>
      ))}
    </div>
  );
}

function ScopeAverageRow({ fleet }) {
  return (
    <div className="compare-row compare-row--foot" role="row" aria-label={t('compare.scopeAverage')}>
      <span className="compare-row__stripe" />
      <span className="compare-row__rank" />
      <span className="compare-row__project compare-row__footLabel">{t('compare.scopeAverage')}</span>
      <span className={`compare-row__score ${scoreColorClass(fleet.score)}`}>{score1(fleet.score)}</span>
      <span className="compare-row__trend"><TrendBadge delta={fleet.delta} /></span>
      <span className="compare-row__viol">
        <span className="compare-row__violTotal">{nf(fleet.totalViolations)}</span>
        <span className="compare-row__sev">
          <SevBadge level="critical" format="count-abbr" count={fleet.severity.critical} />
          <SevBadge level="major" format="count-abbr" count={fleet.severity.major} />
          <SevBadge level="minor" format="count-abbr" count={fleet.severity.minor} />
        </span>
      </span>
      <span className="compare-row__ratio">{complianceRatio(fleet.totalViolations, fleet.totalCompliance)}</span>
      <span className="compare-row__last" />
    </div>
  );
}

/** The ranked projects table: header, one ProjectRow per evaluated project,
 * a collapsed "never evaluated" group, and a scope-average footer row. */
export default function CompareProjectsTable({
  mainRows, unevaluated, fleet, sortDir, scopeCount, onOpenProject, errorsById,
}) {
  const [showUnevaluated, setShowUnevaluated] = useState(false);
  return (
    <section className="compare-panel" aria-label={t('compare.projectsAria')}>
      <div className="compare-panel__head">
        <SectionLabel>{t('compare.projectsHeader', { count: scopeCount })}</SectionLabel>
        <span className="compare-panel__note">
          {sortDir === 'desc' ? t('compare.sortNoteScore') : t('compare.sortNoteScoreAsc')}
          {' · '}
          {t('compare.rowOpenHint')}
        </span>
      </div>
      <div className="compare-table" role="table">
        <div className="compare-row compare-row--head" role="row">
          <span className="compare-row__stripe" />
          <span className="compare-row__rank" />
          <span className="compare-row__project">{t('compare.colProject')}</span>
          <span className="compare-row__score">{t('compare.colScore')}</span>
          <span className="compare-row__trend">{t('compare.colDelta')}</span>
          <span className="compare-row__viol">{t('compare.colViolations')}</span>
          <span className="compare-row__ratio">{t('compare.colRatio')}</span>
          <span className="compare-row__last">{t('compare.colLast')}</span>
        </div>
        {mainRows.map((row, i) => (
          <ProjectRow
            key={row.id}
            row={row}
            rank={i + 1}
            onOpenProject={onOpenProject}
            error={errorsById[row.id]}
          />
        ))}
        {unevaluated.length > 0 && (
          <CollapsedUnevaluated
            unevaluated={unevaluated}
            showUnevaluated={showUnevaluated}
            setShowUnevaluated={setShowUnevaluated}
          />
        )}
        {fleet.scoredCount > 1 && <ScopeAverageRow fleet={fleet} />}
      </div>
    </section>
  );
}
