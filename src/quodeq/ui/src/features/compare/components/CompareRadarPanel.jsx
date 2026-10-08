import { t } from '../../../strings/index.js';
import CompareRadar from './CompareRadar.jsx';
import RadarPanelShell from './RadarPanelShell.jsx';

/**
 * Radar of the active project over the scope average for one dimension.
 * `series` and `active` come from the caller, which owns the hover state.
 */
export default function CompareRadarPanel({ view, axes, series, active = null }) {
  return (
    <RadarPanelShell
      ariaLabel={t('compare.radialAria')}
      header={t('compare.radialHeader', { count: view.principles.length })}
      note={t('compare.radialScale')}
      items={view.principles}
    >
      <CompareRadar axes={axes} series={series} />
      <div className="compare-radar__legend">
        {active && (
          <span className="compare-radar__legendItem compare-radar__legendItem--project">
            {active.row.name}
          </span>
        )}
        <span className="compare-radar__legendItem compare-radar__legendItem--average">
          {t('compare.legendAverage')}
        </span>
      </div>
    </RadarPanelShell>
  );
}
