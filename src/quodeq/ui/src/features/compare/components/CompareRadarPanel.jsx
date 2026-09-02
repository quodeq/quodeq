import { SectionLabel } from '../../../components/terminal/index.js';
import { t } from '../../../strings/index.js';
import CompareRadar from './CompareRadar.jsx';

/**
 * Radar overlaying the leader / trailer / scope average for one dimension
 * (hovering a standings row overlays that project too, via `series`, built
 * by the caller so it can react to hover state without this panel knowing
 * about it).
 */
export default function CompareRadarPanel({ view, axes, series }) {
  return (
    <section className="compare-panel" aria-label={t('compare.radialAria')}>
      <div className="compare-panel__head">
        <SectionLabel>{t('compare.radialHeader', { count: view.principles.length })}</SectionLabel>
        <span className="compare-panel__note">{t('compare.radialScale')}</span>
      </div>
      {view.principles.length >= 3 ? (
        <>
          <CompareRadar axes={axes} series={series} />
          <div className="compare-radar__legend">
            {view.lead && (
              <span className="compare-radar__legendItem compare-radar__legendItem--lead">
                {view.lead.row.name}
              </span>
            )}
            {view.trail && view.trail !== view.lead && (
              <span className="compare-radar__legendItem compare-radar__legendItem--trail">
                {view.trail.row.name}
              </span>
            )}
            <span className="compare-radar__legendItem compare-radar__legendItem--average">
              {t('compare.legendAverage')}
            </span>
          </div>
        </>
      ) : (
        <p className="compare-panel__fallback">{t('compare.radialTooFew')}</p>
      )}
    </section>
  );
}
