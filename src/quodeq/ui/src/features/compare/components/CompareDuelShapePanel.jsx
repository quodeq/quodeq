import { t } from '../../../strings/index.js';
import CompareRadar from './CompareRadar.jsx';
import RadarPanelShell from './RadarPanelShell.jsx';

/** Radar overlaying both projects' shared-dimension scores (needs 3+ shared
 * dimensions to be a legible polygon). */
export default function CompareDuelShapePanel({ sharedDims, a, b }) {
  return (
    <RadarPanelShell
      ariaLabel={t('compare.duelShapeAria')}
      header={t('compare.duelShapeHeader')}
      note={t('compare.duelShapeNote')}
      items={sharedDims}
    >
      <CompareRadar
        axes={sharedDims.map((d) => ({ label: d.label, value: null }))}
        series={[
          { values: sharedDims.map((d) => d.a), variant: 'duelA' },
          { values: sharedDims.map((d) => d.b), variant: 'duelB' },
        ]}
      />
      <div className="compare-radar__legend">
        <span className="compare-duel__legendItem compare-duel__legendItem--a">{a.name}</span>
        <span className="compare-duel__legendItem compare-duel__legendItem--b">{b.name}</span>
      </div>
    </RadarPanelShell>
  );
}
