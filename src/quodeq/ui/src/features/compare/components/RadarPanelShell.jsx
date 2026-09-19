import { SectionLabel } from '../../../components/terminal/index.js';
import { t } from '../../../strings/index.js';

const MIN_RADAR_AXES = 3;

/**
 * The frame both compare radars sit in: labelled section, heading row with a
 * note, and the too-few-axes fallback. A radar needs at least `minItems`
 * axes to be a legible polygon, so `children` only renders once `items` has
 * that many.
 */
export default function RadarPanelShell({ ariaLabel, header, note, items, minItems = MIN_RADAR_AXES, children }) {
  return (
    <section className="compare-panel" aria-label={ariaLabel}>
      <div className="compare-panel__head">
        <SectionLabel>{header}</SectionLabel>
        <span className="compare-panel__note">{note}</span>
      </div>
      {items.length >= minItems
        ? children
        : <p className="compare-panel__fallback">{t('compare.radialTooFew')}</p>}
    </section>
  );
}
