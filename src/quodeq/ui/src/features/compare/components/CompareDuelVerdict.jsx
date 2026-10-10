/**
 * The head-to-head's first answer: who leads and by how much, whether that
 * gap is bigger than the projects' run-to-run swing, and both overall
 * scores. Names are identity-coloured links; scores are grade-coloured.
 */
import { t } from '../../../strings/index.js';
import { tSlots } from '../../../strings/rich.jsx';
import { scoreColorClass } from '../../../utils/formatters.js';
import { scoreToGradeLabel } from '../../../utils/gradeThresholds.js';
import { DUEL_SIGNAL, duelSignal } from '../compareDuelAnalysis.js';
import { DUEL_SIDE } from '../duelTrendGeometry.js';
import { gapClass, score1, signed1 } from './compareDuelShared.jsx';

const SIGNAL_KEY = Object.freeze({
  [DUEL_SIGNAL.CLEAR]: 'compare.duelSignalClear',
  [DUEL_SIGNAL.PROBABLE]: 'compare.duelSignalProbable',
  [DUEL_SIGNAL.NOISE]: 'compare.duelSignalNoise',
  [DUEL_SIGNAL.UNKNOWN]: 'compare.duelSignalUnknown',
});

function SideName({ row, side, onOpenProject }) {
  return (
    <button
      type="button"
      className={`compare-duel-verdict__name compare-duel__name--${side}`}
      onClick={() => onOpenProject(row.id)}
      title={t('compare.openProject')}
    >
      {row.name}
      {row.remote && <span className="compare-row__remote">{t('compare.remoteTag')}</span>}
    </button>
  );
}

function Sentence({ duel, onOpenProject }) {
  const { a, b, gap } = duel;
  const nameA = <SideName row={a} side={DUEL_SIDE.A} onOpenProject={onOpenProject} />;
  const nameB = <SideName row={b} side={DUEL_SIDE.B} onOpenProject={onOpenProject} />;
  if (!gap) return tSlots('compare.duelVerdictEven', { a: nameA, b: nameB });
  const aLeads = gap > 0;
  return tSlots('compare.duelVerdict', {
    lead: aLeads ? nameA : nameB,
    trail: aLeads ? nameB : nameA,
    gap: <span className={`compare-duel__gap compare-duel-verdict__gap ${gapClass(gap)}`}>{signed1(gap)}</span>,
  });
}

function Signal({ duel }) {
  const signal = duelSignal(duel);
  if (!signal) return null;
  return (
    <p className={`compare-duel-verdict__signal compare-duel-verdict__signal--${signal.level}`}>
      {t(SIGNAL_KEY[signal.level], {
        ratio: signal.ratio?.toFixed(1),
        noise: signal.noise?.toFixed(1),
      })}
    </p>
  );
}

function Score({ row, side }) {
  return (
    <div className={`compare-duel-verdict__side compare-duel-verdict__side--${side}`}>
      <span className={`compare-duel-verdict__sideName compare-duel__name--${side}`}>{row.name}</span>
      <span className={`compare-duel-verdict__score ${scoreColorClass(row.score)}`}>{score1(row.score)}</span>
      <span className="compare-duel-verdict__tier">{scoreToGradeLabel(row.score) || t('compare.noRuns')}</span>
    </div>
  );
}

export default function CompareDuelVerdict({ duel, onOpenProject }) {
  return (
    <div className="compare-duel-verdict" role="group" aria-label={t('compare.duelAria')}>
      <div className="compare-duel-verdict__main">
        <p className="compare-duel-verdict__sentence">
          <Sentence duel={duel} onOpenProject={onOpenProject} />
        </p>
        <Signal duel={duel} />
      </div>
      <div className="compare-duel-verdict__scores" role="group" aria-label={t('compare.duelScoresAria')}>
        <Score row={duel.a} side={DUEL_SIDE.A} />
        <Score row={duel.b} side={DUEL_SIDE.B} />
      </div>
    </div>
  );
}
