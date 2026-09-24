import ComparePanel from './ComparePanel.jsx';
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
    <ComparePanel ariaLabel={ariaLabel} header={header} note={note}>
      {items.length >= minItems
        ? children
        : <p className="compare-panel__fallback">{t('compare.radialTooFew')}</p>}
    </ComparePanel>
  );
}
