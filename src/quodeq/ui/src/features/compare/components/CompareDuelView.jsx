/**
 * CompareDuelView — head-to-head between exactly two projects: overall
 * scores with the gap, per-dimension scores as mirrored bars, both trend
 * lines on one time axis, and per-principle diffs for the dimensions the
 * projects share. Reached from the fleet's "compare these two" action when
 * the scope holds exactly two projects.
 *
 * Sides are fixed for the whole screen: A is always the left/first project
 * (accent), B the right/second (info), and every gap reads A minus B.
 */
import { TermHeader, SectionLabel } from '../../../components/terminal/index.js';
import TrendBadge from '../../../components/TrendBadge.jsx';
import { relativeTime } from '../../../components/LastFetchedLine.jsx';
import { scoreColorClass, complianceRatio } from '../../../utils/formatters.js';
import { scoreToGradeLabel } from '../../../utils/gradeThresholds.js';
import { t, LOCALE } from '../../../strings/index.js';
import CompareDuelTrend from './CompareDuelTrend.jsx';
import CompareDuelDimensionsTable from './CompareDuelDimensionsTable.jsx';
import CompareDuelShapePanel from './CompareDuelShapePanel.jsx';
import CompareDuelPrinciples from './CompareDuelPrinciples.jsx';
import { gapClass, score1, signed1 } from './compareDuelShared.jsx';

const nf = (n) => (n == null ? '—' : Number(n).toLocaleString(LOCALE));

/* One half of the versus header: identity-coloured name, grade-coloured
   score, and the side's vitals. */
function VersusSide({ side, row, onOpenProject }) {
  return (
    <div className={`compare-versus__side compare-versus__side--${side}`}>
      <button
        type="button"
        className="compare-versus__name"
        onClick={() => onOpenProject(row.id)}
        title={t('compare.openProject')}
      >
        {row.name}
        {row.remote && <span className="compare-row__remote">{t('compare.remoteTag')}</span>}
      </button>
      <div className="compare-versus__scoreRow">
        <span className={`compare-versus__score ${scoreColorClass(row.score)}`}>{score1(row.score)}</span>
        <span className="compare-versus__tier">{scoreToGradeLabel(row.score) || t('compare.noRuns')}</span>
        <TrendBadge delta={row.delta ?? row.lastDelta} />
      </div>
      <div className="compare-versus__meta">
        <span>{t('compare.violCount', { count: nf(row.totalViolations) })}</span>
        <span>{complianceRatio(row.totalViolations, row.totalCompliance)}</span>
        <span className={row.stale ? 'compare-row__last--stale' : undefined}>
          {relativeTime(row.lastISO) || '—'}
        </span>
        {row.commitsSince != null && row.commitsSince > 0 && (
          <span className="compare-rowdetail__stale">
            {t('compare.commitsSince', { count: nf(row.commitsSince) })}
          </span>
        )}
      </div>
    </div>
  );
}

function DuelTrendPanel({ trend, a, b, onOpenProject }) {
  const trendPoints = trend.a.length + trend.b.length;
  return (
    <section className="compare-panel" aria-label={t('compare.duelTrendAria')}>
      <div className="compare-panel__head">
        <SectionLabel>{t('compare.duelTrendHeader')}</SectionLabel>
        <span className="compare-panel__note">{t('compare.duelTrendNote')}</span>
      </div>
      {trendPoints >= 2 ? (
        <>
          <CompareDuelTrend a={trend.a} b={trend.b} />
          <div className="compare-radar__legend">
            <button
              type="button"
              className="compare-duel__legendItem compare-duel__legendItem--a"
              onClick={() => onOpenProject(a.id)}
            >
              {a.name}
            </button>
            <button
              type="button"
              className="compare-duel__legendItem compare-duel__legendItem--b"
              onClick={() => onOpenProject(b.id)}
            >
              {b.name}
            </button>
          </div>
        </>
      ) : (
        <p className="compare-panel__fallback">{t('compare.duelTrendTooFew')}</p>
      )}
    </section>
  );
}

function duelGapHint(duel, a, b) {
  if (duel.gap == null) return '';
  if (duel.gap === 0) return t('compare.duelEven');
  return t('compare.duelLeads', {
    name: duel.gap > 0 ? a.name : b.name,
    gap: Math.abs(duel.gap).toFixed(1),
  });
}

/** Title + the versus header: both sides' vitals with the gap between them. */
function CompareDuelHeader({ duel, a, b, onOpenProject }) {
  return (
    <>
      <div className="compare-page__top">
        {/* No local back button — the app breadcrumb already walks back,
            same as the dimension screen. */}
        <div className="compare-page__titles">
          <TermHeader
            name={t('compare.duelTitle')}
            sub={t('compare.duelSubtitle', { a: a.name, b: b.name, count: duel.sharedCount })}
          />
        </div>
      </div>

      <div className="compare-versus" role="group" aria-label={t('compare.duelAria')}>
        <VersusSide side="a" row={a} onOpenProject={onOpenProject} />
        <div className="compare-versus__gap">
          <span className="compare-versus__gapLabel">{t('compare.duelCardGap')}</span>
          <span className={`compare-versus__gapValue ${gapClass(duel.gap)}`}>
            {duel.gap != null ? signed1(duel.gap) : '—'}
          </span>
          <span className="compare-versus__gapHint">{duelGapHint(duel, a, b)}</span>
        </div>
        <VersusSide side="b" row={b} onOpenProject={onOpenProject} />
      </div>
    </>
  );
}

export default function CompareDuelView({ duel, onOpenProject }) {
  const { a, b } = duel;
  const sharedDims = duel.dimensions.filter((d) => d.shared);

  return (
    <>
      <CompareDuelHeader duel={duel} a={a} b={b} onOpenProject={onOpenProject} />

      {!duel.ready ? (
        <section className="compare-panel" aria-label={t('compare.duelAria')}>
          <p className="compare-panel__fallback">{t('compare.duelNeedsBoth')}</p>
        </section>
      ) : (
        <>
          <CompareDuelDimensionsTable dimensions={duel.dimensions} />

          <div className="compare-lower compare-lower--duel">
            <CompareDuelShapePanel sharedDims={sharedDims} a={a} b={b} />
            <DuelTrendPanel trend={duel.trend} a={a} b={b} onOpenProject={onOpenProject} />
          </div>

          <CompareDuelPrinciples principles={duel.principles} dimensions={duel.dimensions} />
        </>
      )}
    </>
  );
}
