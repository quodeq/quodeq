import { TermHeader, StatStrip, SectionLabel } from '../../../components/terminal/index.js';
import { t } from '../../../strings/index.js';

// Skeleton frame for the Overview's guaranteed content: the stat-strip hero
// and the quality-dimensions grid. Rides the same classes the real
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

// Representative placeholder count -- the real grid's card count varies per
// project (server-filtered by visible standards, see readVisibleStandardIds),
// there is no fixed list to mirror here.
const DIMENSION_CARD_COUNT = 6;

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
    </div>
  );
}
