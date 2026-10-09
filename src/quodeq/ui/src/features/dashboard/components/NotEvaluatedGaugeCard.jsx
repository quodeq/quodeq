/**
 * NotEvaluatedGaugeCard: a standard switched on in Standards that has no
 * evaluation yet. Drawn as an empty dashed gauge in the dimension grid so the
 * switch visibly did something; clicking it opens Evaluate.
 */
import { t } from '../../../strings/index.js';

// Same geometry as DimensionGaugeCard's ring, so the cards line up.
const RING_SIZE = 100;
const RING_STROKE = 8;
const RING_RADIUS = (RING_SIZE - RING_STROKE) / 2;
const RING_C = RING_SIZE / 2;
// The dash stands a little above centre, the two-line label below it.
const DASH_RISE = 4;
const LABEL_FIRST_DROP = 13;
const LABEL_SECOND_DROP = 22;
const DASH_Y = RING_C - DASH_RISE;
const LABEL_FIRST_Y = RING_C + LABEL_FIRST_DROP;
const LABEL_SECOND_Y = RING_C + LABEL_SECOND_DROP;

export default function NotEvaluatedGaugeCard({ name, onActivate }) {
  return (
    <button
      type="button"
      className="dim-gauge-card dim-gauge-card--not-evaluated"
      onClick={onActivate}
      aria-label={t('overview.notEvaluatedAria', { name })}
    >
      <span className="dim-gauge-card__head">
        <span className="dim-gauge-card__name">{name}</span>
      </span>
      <span className="dim-gauge-card__gauge dim-gauge-card__gauge--insuf" aria-hidden="true">
        <svg width={RING_SIZE} height={RING_SIZE} viewBox={`0 0 ${RING_SIZE} ${RING_SIZE}`}>
          <circle className="dim-gauge-card__ring-bg" cx={RING_C} cy={RING_C} r={RING_RADIUS} strokeWidth={RING_STROKE} strokeDasharray="3 4" />
          <text className="dim-gauge-card__score" x={RING_C} y={DASH_Y}>{t('overview.notEvaluatedScore')}</text>
          <text className="dim-gauge-card__grade dim-gauge-card__grade--small" x={RING_C} y={LABEL_FIRST_Y}>{t('overview.notEvaluatedLineOne')}</text>
          <text className="dim-gauge-card__grade dim-gauge-card__grade--small" x={RING_C} y={LABEL_SECOND_Y}>{t('overview.notEvaluatedLineTwo')}</text>
        </svg>
      </span>
      <span className="dim-gauge-card__insuf-line">{t('overview.notEvaluatedHint')}</span>
    </button>
  );
}
