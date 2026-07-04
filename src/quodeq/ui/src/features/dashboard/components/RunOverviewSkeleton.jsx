import { TermHeader, StatStrip, Stat, SectionLabel } from '../../../components/terminal/index.js';

const STAT_LABELS = ['SCORE', 'VIOLATIONS', 'COMPLIANCE', 'RATIO'];
const DIMENSION_CARD_COUNT = 6;

function Block({ width }) {
  return <span className="run-skel__block" style={{ width }} aria-hidden="true" />;
}

/**
 * Loading placeholder for the run detail view.
 *
 * Mirrors the RunOverviewPanel layout (hero header + stat cards + dimension
 * grid) so entering a run keeps the page structure stable instead of
 * blanking to a full-screen spinner. The run date is already known from the
 * navigation params, so the header renders it immediately.
 */
export default function RunOverviewSkeleton({ dateLabel }) {
  return (
    <div className="run-overview-fade run-overview-ready run-skel" role="status" aria-label="Loading run details">
      <section className="acc-eval-panel acc-eval-panel--terminal">
        <div className="acc-eval-panel__top">
          <TermHeader name="run" sub={dateLabel || <Block width="10ch" />} />
        </div>
        <StatStrip cards>
          {STAT_LABELS.map((label) => (
            <Stat key={label} label={label} value={<Block width="3ch" />} hint={<Block width="9ch" />} />
          ))}
        </StatStrip>
      </section>
      <section className="quality-dimensions" aria-hidden="true">
        <div className="quality-dimensions__head">
          <SectionLabel>quality_dimensions</SectionLabel>
        </div>
        <div className="dimensions-panel">
          <div className="dimensions-grid">
            {Array.from({ length: DIMENSION_CARD_COUNT }, (_, i) => (
              <div key={i} className="run-skel__card" />
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
