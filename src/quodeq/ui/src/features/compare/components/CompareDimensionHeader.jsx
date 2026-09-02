import { TermHeader } from '../../../components/terminal/index.js';
import TrendBadge from '../../../components/TrendBadge.jsx';
import { scoreColorClass } from '../../../utils/formatters.js';
import { scoreToGradeLabel } from '../../../utils/gradeThresholds.js';
import { t, LOCALE } from '../../../strings/index.js';

const nf = (n) => (n == null ? '—' : Number(n).toLocaleString(LOCALE));

/** Title/subtitle + the dimension tab bar (switches sideways between
 * dimensions without a local back button — the app breadcrumb walks back). */
export default function CompareDimensionHeader({ view, board, onOpenDimension }) {
  return (
    <div className="compare-page__top">
      <div className="compare-page__titles">
        <TermHeader
          name={view.label}
          sub={t('compare.dimSubtitle', {
            principles: view.principles.length,
            violations: nf(view.violations),
            projects: view.standings.length,
          })}
          badge={(
            <span className="compare-dim-badges">
              <span className={`compare-dim-tier ${scoreColorClass(view.avg)}`}>
                {scoreToGradeLabel(view.avg) || ''}
              </span>
              <TrendBadge delta={view.delta} />
            </span>
          )}
        />
      </div>
      <div className="compare-header__controls">
        <span className="compare-sort" role="group" aria-label={t('compare.dimTabsAria')}>
          {board.map((b) => (
            <button
              key={b.key}
              type="button"
              className={`compare-sort__btn${b.key === view.key ? ' compare-sort__btn--on' : ''}`}
              onClick={() => onOpenDimension(b.key)}
            >
              {b.label.slice(0, 5)}
            </button>
          ))}
        </span>
      </div>
    </div>
  );
}
