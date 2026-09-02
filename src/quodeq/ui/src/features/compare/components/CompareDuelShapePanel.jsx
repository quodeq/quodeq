import { SectionLabel } from '../../../components/terminal/index.js';
import { t } from '../../../strings/index.js';
import CompareRadar from './CompareRadar.jsx';

/** Radar overlaying both projects' shared-dimension scores (needs 3+ shared
 * dimensions to be a legible polygon). */
export default function CompareDuelShapePanel({ sharedDims, a, b }) {
  return (
    <section className="compare-panel" aria-label={t('compare.duelShapeAria')}>
      <div className="compare-panel__head">
        <SectionLabel>{t('compare.duelShapeHeader')}</SectionLabel>
        <span className="compare-panel__note">{t('compare.duelShapeNote')}</span>
      </div>
      {sharedDims.length >= 3 ? (
        <>
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
        </>
      ) : (
        <p className="compare-panel__fallback">{t('compare.radialTooFew')}</p>
      )}
    </section>
  );
}
