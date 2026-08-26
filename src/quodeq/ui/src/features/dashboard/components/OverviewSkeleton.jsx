import { TermHeader, StatStrip, SectionLabel } from '../../../components/terminal/index.js';
import { t } from '../../../strings/index.js';
import RunHistoryPanelPlaceholder from './RunHistoryPanelPlaceholder.jsx';

// Skeleton frame for the Overview's full footprint: the stat-strip hero,
// the score-history + dimensions-table row, the quality-dimensions grid,
// and the offending-files table. Rides the same classes the real
// AccumulatedHeroSection / AccumulatedDimensionsSection / DimensionGaugeCard
// render (dashboard.css / terminal.css / dim-gauge-card.css) so the footprint
// (card sizes, grid gaps, min-heights) matches exactly -- only the label/
// value/gauge content areas are swapped for static dimmed blocks (house
// idiom: SidePane's body-skeleton spans, SidePane.css:186-201 -- no shimmer,
// no animation). Shown for the Overview only, in place of the inline
// LoadingScreen, for both windows DashboardPage can be waiting in (before the
// dashboard payload lands, and again if scoring is still catching up after it
// does), so it reads as one continuous skeleton rather than a loader-to-
// skeleton handoff.
//
// Real `<Stat>`/`<DimensionGaugeCard>` render actual numbers/labels as text;
// this component hand-rolls the same class names instead of reusing those
// components so every content slot can be a dimmed block rather than real
// text with nothing to show yet.

const STAT_SLOTS = ['score', 'violations', 'compliance', 'ratio'];

// Representative placeholder counts -- the real grid's card count varies per
// project (server-filtered by visible standards, see readVisibleStandardIds),
// there is no fixed list to mirror here. Same idea for the score-history
// chart (only mounted with >=2 days of trend) and the offending-files table
// (only rendered when a project has offenders): both are the common case,
// so the skeleton reserves them rather than let data arrival grow the page.
const DIMENSION_CARD_COUNT = 6;
const DIM_SCORE_ROW_COUNT = 6;
const OFFENDING_FILE_ROW_COUNT = 5;

function SkeletonStat({ slot }) {
  return (
    <div className="term-stat term-stat--default" aria-hidden="true" data-slot={slot}>
      <div className="term-stat__label">
        <span className="overview-skeleton__bar overview-skeleton__bar--label" />
      </div>
      <div className="term-stat__value-row">
        <span className="overview-skeleton__bar overview-skeleton__bar--value" />
      </div>
      <div className="term-stat__hint">
        <span className="overview-skeleton__bar overview-skeleton__bar--hint" />
      </div>
    </div>
  );
}

function SkeletonDimensionCard({ index }) {
  return (
    <article className="dim-gauge-card" aria-hidden="true" data-skeleton-index={index}>
      <div className="dim-gauge-card__head">
        <span className="overview-skeleton__bar overview-skeleton__bar--name" />
      </div>
      <div className="dim-gauge-card__gauge">
        <span className="overview-skeleton__bar overview-skeleton__bar--gauge" />
      </div>
      <div className="dim-gauge-card__meta">
        <span className="overview-skeleton__bar overview-skeleton__bar--meta" />
      </div>
      <div className="dim-gauge-card__sev-row">
        <span className="overview-skeleton__bar overview-skeleton__bar--sev" />
      </div>
    </article>
  );
}

function SkeletonDimScoreRow({ index }) {
  return (
    <div className="dim-score-row dim-score-row--terminal" data-skeleton-index={index}>
      <span className="dim-score-label"><span className="overview-skeleton__bar overview-skeleton__bar--dim-label" /></span>
      <span className="dim-score-spark"><span className="overview-skeleton__bar overview-skeleton__bar--spark" /></span>
      <span className="dim-score-value"><span className="overview-skeleton__bar overview-skeleton__bar--dim-value" /></span>
      <span className="dim-score-trend"><span className="overview-skeleton__bar overview-skeleton__bar--dim-trend" /></span>
      <span className="dim-score-viol"><span className="overview-skeleton__bar overview-skeleton__bar--dim-viol" /></span>
    </div>
  );
}

/**
 * @param {object} props
 * @param {string} [props.projectName] The project being loaded, carried in
 *   the header sub line so the wait still names what it's waiting on.
 */
export default function OverviewSkeleton({ projectName }) {
  return (
    <div className="overview-skeleton" aria-busy="true">
      <section className="acc-eval-panel acc-eval-panel--terminal">
        <div className="acc-eval-panel__top">
          <TermHeader name={t('overview.termName')} sub={projectName ? t('overview.loadingProject', { name: projectName }) : t('overview.loading')} />
        </div>
        <StatStrip cards>
          {STAT_SLOTS.map((slot) => <SkeletonStat key={slot} slot={slot} />)}
        </StatStrip>
      </section>
      <div className="history-panels-row" aria-hidden="true">
        <RunHistoryPanelPlaceholder />
        <section className="dim-score-panel dim-score-panel--terminal panel">
          <header className="dim-score-panel__header">{t('overview.dimensionsHeader')}</header>
          <div className="dim-score-rows">
            {Array.from({ length: DIM_SCORE_ROW_COUNT }, (_, index) => (
              <SkeletonDimScoreRow key={index} index={index} />
            ))}
          </div>
        </section>
      </div>
      <section className="quality-dimensions" aria-hidden="true">
        <div className="quality-dimensions__head">
          <SectionLabel>{t('overview.qualityDimensionsLabel')}</SectionLabel>
        </div>
        <div className="dimensions-panel">
          <div className="dimensions-grid">
            {Array.from({ length: DIMENSION_CARD_COUNT }, (_, index) => (
              <SkeletonDimensionCard key={index} index={index} />
            ))}
          </div>
        </div>
      </section>
      <section className="qd-cards-panel offending-panel" aria-hidden="true">
        <div className="qd-cards-panel__head">
          <SectionLabel>{t('overview.violationsByFileLabel')}</SectionLabel>
        </div>
        {Array.from({ length: OFFENDING_FILE_ROW_COUNT }, (_, index) => (
          <span key={index} className="overview-skeleton__bar overview-skeleton__file-row" />
        ))}
      </section>
    </div>
  );
}
