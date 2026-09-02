import SevBadge from '../../../components/terminal/SevBadge.jsx';
import TrendBadge from '../../../components/TrendBadge.jsx';
import CompareTrendLine from './CompareTrendLine.jsx';
import { relativeTime } from '../../../components/LastFetchedLine.jsx';
import { scoreColorClass, scoreGradeColorVar, complianceRatio } from '../../../utils/formatters.js';
import { t, LOCALE } from '../../../strings/index.js';
import { consequenceOf, consequenceLevel } from '../compareModel.js';

const nf = (n) => (n == null ? '—' : Number(n).toLocaleString(LOCALE));
const score1 = (s) => (s == null ? '—' : (Math.round(s * 10) / 10).toFixed(1));

/* Score, 30-day spark + delta, violations split by severity, ratio and
   freshness — everything a row shows once it has a score. */
function ProjectRowStats({ row }) {
  return (
    <>
      {/* Number + grade colour only — the tier word ("good",
          "adequate") repeated what both already say. */}
      <span className="compare-row__score">
        <span className={scoreColorClass(row.score)}>{score1(row.score)}</span>
      </span>
      <span className="compare-row__trend">
        {row.spark.length > 1 && <CompareTrendLine scores={row.spark} />}
        {row.delta != null ? (
          <TrendBadge delta={row.delta} />
        ) : row.lastDelta != null ? (
          <span className="compare-delta--old" title={t('compare.oldDeltaTip')}>
            <TrendBadge delta={row.lastDelta} />
          </span>
        ) : null}
      </span>
      {/* Severity split on wide views; small tiers swap it for the
          bare total (see the small-view tiers in compare.css). */}
      <span
        className="compare-row__viol"
        title={t('compare.ratioTip', { pass: nf(row.totalCompliance), checks: nf(row.totalCompliance + row.totalViolations) })}
      >
        <span className="compare-row__violTotal">{nf(row.totalViolations)}</span>
        <span className="compare-row__sev">
          <SevBadge level="critical" format="count-abbr" count={row.severity.critical} />
          <SevBadge level="major" format="count-abbr" count={row.severity.major} />
          <SevBadge level="minor" format="count-abbr" count={row.severity.minor} />
        </span>
      </span>
      <span
        className="compare-row__ratio"
        title={t('compare.ratioTip', { pass: nf(row.totalCompliance), checks: nf(row.totalCompliance + row.totalViolations) })}
      >
        {complianceRatio(row.totalViolations, row.totalCompliance)}
      </span>
      <span className={`compare-row__last${row.stale ? ' compare-row__last--stale' : ''}`}>
        {relativeTime(row.lastISO) || '—'}
        {row.commitsSince != null && row.commitsSince > 0 && (
          <span className="compare-row__behind">
            {' · '}
            {t('compare.behindShort', { count: nf(row.commitsSince) })}
          </span>
        )}
      </span>
    </>
  );
}

/* One line per project — the row IS the summary now: identity, score,
   30-day spark + delta, violations split by severity, freshness with
   commits-behind. The score matrix below already carries every
   per-dimension number, so the old expansion (chips, facts, per-row duel)
   had nothing left to say; the name opens the project, the same gesture as
   every other list on this screen, and the header duel button covers
   head-to-heads. */
export default function ProjectRow({ row, rank, onOpenProject, error }) {
  const level = consequenceLevel(consequenceOf(row));
  return (
    <div
      className={`compare-rowgroup compare-rowgroup--${level}`}
      // The stripe's colour is the project's GRADE; the consequence level
      // only decides whether a stripe shows.
      style={row.hasData ? { '--row-accent': scoreGradeColorVar(row.score) } : undefined}
    >
      <div className={`compare-row${row.hasData ? '' : ' compare-row--nodata'}`} role="row">
        <span className="compare-row__stripe" aria-hidden="true" />
        <span className="compare-row__rank">{rank}</span>
        <span className="compare-row__project">
          <button
            type="button"
            className="compare-row__name compare-row__namebtn"
            title={row.name}
            onClick={() => onOpenProject(row.id)}
          >
            {row.name}
          </button>
          {row.lang && <span className="compare-row__meta">{row.lang}</span>}
          {row.remote && <span className="compare-row__remote">{t('compare.remoteTag')}</span>}
        </span>
        {row.hasData ? (
          <ProjectRowStats row={row} />
        ) : (
          <span className="compare-row__pending">
            {error
              ? t('compare.loadFailed')
              : row.loaded
                ? t('compare.noRuns')
                : t('compare.computing')}
          </span>
        )}
      </div>
    </div>
  );
}
