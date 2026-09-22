import { TermHeader } from '../../../components/terminal/index.js';
import TrendBadge from '../../../components/TrendBadge.jsx';
import { scoreColorClass } from '../../../utils/formatters.js';
import { scoreToGradeLabel } from '../../../utils/gradeThresholds.js';
import { t } from '../../../strings/index.js';
import { nf, TAB_LABEL_CHARS } from '../compareFormatters.js';


/* One panel region holds whichever dimension is open, so every tab controls
   the same element and points at this id. CompareDimensionView puts it on
   the body it renders below this header. */
export const DIMENSION_PANEL_ID = 'compare-dimension-panel';
export const dimensionTabId = (key) => `compare-dimension-tab-${key}`;

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
        {/* A tab bar in behaviour as well as looks: each button switches the
            screen below it, so the open dimension needs aria-selected and not
            just the --on class to be announced (U-ACC-1). */}
        <span className="compare-sort" role="tablist" aria-label={t('compare.dimensionTabsAria')}>
          {board.map((b) => {
            const isSelected = b.key === view.key;
            return (
              <button
                key={b.key}
                type="button"
                role="tab"
                id={dimensionTabId(b.key)}
                aria-selected={isSelected}
                aria-controls={DIMENSION_PANEL_ID}
                /* The visible text is clipped to five characters, so the
                   whole dimension name has to come from the label. */
                aria-label={b.label}
                className={`compare-sort__btn${isSelected ? ' compare-sort__btn--on' : ''}`}
                onClick={() => onOpenDimension(b.key)}
              >
                {b.label.slice(0, TAB_LABEL_CHARS)}
              </button>
            );
          })}
        </span>
      </div>
    </div>
  );
}
