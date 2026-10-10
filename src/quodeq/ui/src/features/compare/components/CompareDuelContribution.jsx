/**
 * Where the overall gap comes from: each shared dimension's share of it as
 * a bar from a centre line, in the colour of the side it helps (A grows
 * left, B right), with the dimension's raw gap beside it. The shares add up
 * to the overall gap; dimensions only one side has, plus rounding, are the
 * last row.
 */
import { t } from '../../../strings/index.js';
import ComparePanel from './ComparePanel.jsx';
import { gapContributions } from '../compareDuelAnalysis.js';
import { DUEL_SIDE } from '../duelTrendGeometry.js';
import { gapClass, signed1 } from './compareDuelShared.jsx';
import { PERCENT } from '../../../constants.js';

// The widest bar fills its half; a scale floor keeps tiny gaps from looking huge.
const MIN_SCALE = 0.3;

function Bar({ value, max }) {
  const pct = `${(Math.abs(value) / max) * PERCENT}%`;
  return (
    <span className="compare-duel-contrib__track" aria-hidden="true">
      <span className="compare-duel-contrib__half compare-duel-contrib__half--a">
        {value > 0 && <span className={`compare-duel-contrib__bar compare-duel__fill--${DUEL_SIDE.A}`} style={{ width: pct }} />}
      </span>
      <span className="compare-duel-contrib__half">
        {value < 0 && <span className={`compare-duel-contrib__bar compare-duel__fill--${DUEL_SIDE.B}`} style={{ width: pct }} />}
      </span>
    </span>
  );
}

export default function CompareDuelContribution({ duel }) {
  const rows = gapContributions(duel);
  const max = Math.max(MIN_SCALE, ...rows.map((r) => Math.abs(r.value)));
  return (
    <ComparePanel
      ariaLabel={t('compare.duelContribAria')}
      header={t('compare.duelContribHeader')}
      note={t('compare.duelContribNote', { gap: signed1(duel.gap) })}
    >
      {rows.length ? (
        <ul className="compare-duel-contrib">
          {rows.map((r) => (
            <li key={r.key} className={`compare-duel-contrib__row${r.rest ? ' compare-duel-contrib__row--rest' : ''}`}>
              <span className="compare-duel-contrib__label">{r.rest ? t('compare.duelContribRest') : r.label}</span>
              <Bar value={r.value} max={max} />
              <span className={`compare-duel-contrib__value ${gapClass(r.value)}`}>{signed1(r.value)}</span>
              <span className="compare-duel-contrib__raw">{r.gap != null ? t('compare.duelContribRaw', { gap: signed1(r.gap) }) : ''}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="compare-panel__fallback">{t('compare.duelNoShared')}</p>
      )}
    </ComparePanel>
  );
}
