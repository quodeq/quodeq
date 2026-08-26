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
import CompareRadar from './CompareRadar.jsx';

const nf = (n) => (n == null ? '—' : Number(n).toLocaleString(LOCALE));
const score1 = (s) => (s == null ? '—' : (Math.round(s * 10) / 10).toFixed(1));
const signed1 = (g) => (g > 0 ? `+${g.toFixed(1)}` : g.toFixed(1));

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

function gapClass(gap) {
  if (gap == null || gap === 0) return 'compare-duel__gap--even';
  return gap > 0 ? 'compare-duel__gap--a' : 'compare-duel__gap--b';
}

/** Mirrored score bars growing from a shared centre line. */
function DuelBars({ a, b }) {
  return (
    <span className="compare-duel__bars" aria-hidden="true">
      <span className="compare-duel__barLane compare-duel__barLane--a">
        {a != null && (
          <span className="compare-duel__bar compare-duel__bar--a" style={{ width: `${a * 10}%` }} />
        )}
      </span>
      <span className="compare-duel__barLane compare-duel__barLane--b">
        {b != null && (
          <span className="compare-duel__bar compare-duel__bar--b" style={{ width: `${b * 10}%` }} />
        )}
      </span>
    </span>
  );
}

export default function CompareDuelView({ duel, onBack, onOpenProject }) {
  const { a, b } = duel;
  const gapHint = duel.gap == null
    ? ''
    : duel.gap === 0
      ? t('compare.duelEven')
      : t('compare.duelLeads', {
        name: duel.gap > 0 ? a.name : b.name,
        gap: Math.abs(duel.gap).toFixed(1),
      });
  const trendPoints = duel.trend.a.length + duel.trend.b.length;
  const sharedDims = duel.dimensions.filter((d) => d.shared);

  return (
    <>
      <div className="compare-page__top">
        <div className="compare-page__titles">
          <button type="button" className="compare-back" onClick={onBack}>
            ‹ {t('compare.duelBack')}
          </button>
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
          <span className="compare-versus__gapHint">{gapHint}</span>
        </div>
        <VersusSide side="b" row={b} onOpenProject={onOpenProject} />
      </div>

      {!duel.ready ? (
        <section className="compare-panel" aria-label={t('compare.duelAria')}>
          <p className="compare-panel__fallback">{t('compare.duelNeedsBoth')}</p>
        </section>
      ) : (
        <>
          <section className="compare-panel" aria-label={t('compare.duelDimsAria')}>
            <div className="compare-panel__head">
              <SectionLabel>{t('compare.dimensionsHeader', { count: duel.dimensions.length })}</SectionLabel>
              <span className="compare-panel__note">{t('compare.duelDimsNote')}</span>
            </div>
            <ul className="compare-duel-dims">
              {duel.dimensions.map((d) => (
                <li key={d.key} className="compare-duel-dims__row">
                  <span className="compare-duel-dims__label">{d.label}</span>
                  <span className={`compare-duel-dims__score ${scoreColorClass(d.a)}`}>{score1(d.a)}</span>
                  <DuelBars a={d.a} b={d.b} />
                  <span className={`compare-duel-dims__score ${scoreColorClass(d.b)}`}>{score1(d.b)}</span>
                  <span className={`compare-duel__gap ${gapClass(d.gap)}`}>
                    {d.gap != null ? signed1(d.gap) : '—'}
                  </span>
                </li>
              ))}
            </ul>
          </section>

          <div className="compare-lower compare-lower--duel">
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

            <section className="compare-panel" aria-label={t('compare.duelTrendAria')}>
              <div className="compare-panel__head">
                <SectionLabel>{t('compare.duelTrendHeader')}</SectionLabel>
                <span className="compare-panel__note">{t('compare.duelTrendNote')}</span>
              </div>
              {trendPoints >= 2 ? (
                <>
                  <CompareDuelTrend a={duel.trend.a} b={duel.trend.b} />
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
          </div>

          <section className="compare-panel" aria-label={t('compare.duelPrinciplesAria')}>
            <div className="compare-panel__head">
              <SectionLabel>
                {t('compare.duelPrinciplesHeader', {
                  count: duel.principles.reduce((n, g) => n + g.items.length, 0),
                })}
              </SectionLabel>
              <span className="compare-panel__note">{t('compare.duelPrinciplesNote')}</span>
            </div>
            {duel.principles.length ? (
              <div className="compare-duel-principles">
                {duel.principles.map((group) => {
                  // The group IS a dimension: repeat its two scores and gap
                  // in the heading so the diff reads without scrolling back
                  // up to the dimensions table.
                  const dim = duel.dimensions.find((d) => d.key === group.key);
                  return (
                  <article key={group.key} className="compare-duel-principles__group">
                    <h3 className="compare-duel-principles__dim">
                      <span className="compare-duel-principles__dimLabel">{group.label}</span>
                      {dim && (
                        /* Legend-style side swatches (the same dash language
                           the charts' legends use) tie each number to its
                           side without repeating the row bars up here. */
                        <span className="compare-duel-principles__dimScores">
                          <span className="compare-duel-principles__side compare-duel-principles__side--a" aria-hidden="true" />
                          <span className={scoreColorClass(dim.a)}>{score1(dim.a)}</span>
                          <span className="compare-duel-principles__side compare-duel-principles__side--b" aria-hidden="true" />
                          <span className={scoreColorClass(dim.b)}>{score1(dim.b)}</span>
                          <span className={`compare-duel__gap ${gapClass(dim.gap)}`}>
                            {dim.gap != null ? signed1(dim.gap) : '—'}
                          </span>
                        </span>
                      )}
                    </h3>
                    <ul className="compare-duel-principles__list">
                      {group.items.map((p) => (
                        <li key={p.key} className="compare-duel-principles__row">
                          <span className="compare-duel-principles__label">{p.label}</span>
                          <span className={`compare-duel-principles__score ${scoreColorClass(p.a)}`}>{score1(p.a)}</span>
                          <DuelBars a={p.a} b={p.b} />
                          <span className={`compare-duel-principles__score ${scoreColorClass(p.b)}`}>{score1(p.b)}</span>
                          <span className={`compare-duel__gap ${gapClass(p.gap)}`}>
                            {p.gap != null ? signed1(p.gap) : '—'}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </article>
                  );
                })}
              </div>
            ) : (
              <p className="compare-panel__fallback">{t('compare.duelNoShared')}</p>
            )}
          </section>
        </>
      )}
    </>
  );
}
