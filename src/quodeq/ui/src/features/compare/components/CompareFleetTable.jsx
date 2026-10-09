/**
 * Projects ranked: one row per project with its score on a shared axis
 * against the fleet average (grade zones behind it), the 30-day movement,
 * size, and exposure per size (violations per 100 files, critical per
 * 1,000), then freshness. A column header ranks by it; again reverses.
 * The axis fits the overall scores, not the dimension lows.
 *
 * Rows still computing or failed to load stay listed at the bottom;
 * never-evaluated projects collapse into one line. On a phone only rank,
 * name, score and 30d remain, and a red dot replaces the last-scan column.
 */
import { useState } from 'react';
import { t } from '../../../strings/index.js';
import { relativeTime } from '../../../components/LastFetchedLine.jsx';
import { scoreColorClass, scoreGradeColorVar } from '../../../utils/formatters.js';
import ComparePanel from './ComparePanel.jsx';
import CompareDeltaBadge from './CompareDeltaBadge.jsx';
import CompareSortButton from './CompareSortButton.jsx';
import { FLEET_SORT, sortFleet } from '../compareFleetOverview.js';
import { exposureOf } from '../compareDuelAnalysis.js';
import { scoreAxisFor } from '../compareDuelTable.js';
import { nf, score1 } from '../compareFormatters.js';

const NONE = '·';
// Coverage under this share of files reads as a caution.
const LOW_COVERAGE_PCT = 80;
const fixed1 = (v) => (v == null ? NONE : v.toFixed(1));
const pct = (v) => `${v}%`;

function ScoreDot({ score, axis, fleetScore }) {
  const at = axis.at(score);
  const avg = axis.at(fleetScore);
  return (
    <span className="compare-fleetplot" aria-hidden="true">
      {axis.zones.slice(1).map((z) => <span key={z.label} className="compare-fleetplot__zone" style={{ left: `${axis.at(z.from)}%` }} />)}
      <span className="compare-fleetplot__avg" style={{ left: `${avg}%` }} />
      <span className="compare-fleetplot__bar" style={{ left: `${Math.min(at, avg)}%`, width: `${Math.abs(at - avg)}%` }} />
      <span className="compare-fleetplot__dot" style={{ left: `${at}%`, '--dot': scoreGradeColorVar(score) }} />
    </span>
  );
}

function Head({ axis, sort, onSort, hasCoverage }) {
  const col = (key, label) => <CompareSortButton sortKey={key} label={label} sort={sort} onSort={onSort} className="compare-fleettable__num" />;
  return (
    <div className={`compare-fleettable__row compare-fleettable__row--head${hasCoverage ? ' compare-fleettable__row--cov' : ''}`}>
      <span aria-hidden="true">{t('compare.colRank')}</span>
      <span>{t('compare.colProject')}</span>
      <span className="compare-fleettable__axis" aria-hidden="true">
        {axis.zones.map((z) => (
          <span key={z.label} className="compare-fleettable__zone" style={{ left: `${axis.at(z.from)}%`, width: `${axis.at(z.to) - axis.at(z.from)}%` }}>{z.label}</span>
        ))}
        {axis.ticks.map((v) => <span key={v} className="compare-fleettable__tick" style={{ left: `${axis.at(v)}%` }}>{v}</span>)}
      </span>
      {col(FLEET_SORT.SCORE, t('compare.colScoreShort'))}
      {col(FLEET_SORT.MOVE, t('compare.col30d'))}
      {col(FLEET_SORT.FILES, t('compare.colFiles'))}
      {hasCoverage && <span className="compare-fleettable__num">{t('compare.colAnalysed')}</span>}
      {col(FLEET_SORT.DENSITY, t('compare.colDensity'))}
      {col(FLEET_SORT.CRITICAL, t('compare.colCriticalK'))}
      {col(FLEET_SORT.FRESH, t('compare.colLastScan'))}
    </div>
  );
}

function Name({ row, onOpenProject }) {
  return (
    <span className="compare-fleettable__name">
      <button type="button" className="compare-fleettable__namebtn" title={row.name} onClick={() => onOpenProject(row.id)}>{row.name}</button>
      {row.stale && <span className="compare-fleettable__staledot" title={t('compare.staleDot')} />}
      {row.lang && <span className="compare-fleettable__lang">{row.lang}</span>}
      {row.remote && <span className="compare-row__remote">{t('compare.remoteTag')}</span>}
    </span>
  );
}

function Row({ row, rank, axis, fleetScore, hasCoverage, hover, setHover, onOpenProject }) {
  const e = exposureOf(row);
  const caution = (on) => (on ? ' compare-fleettable__warn' : '');
  return (
    <li
      className={`compare-fleettable__row${hasCoverage ? ' compare-fleettable__row--cov' : ''}${hover === row.id ? ' is-hovered' : ''}`}
      onMouseEnter={() => setHover(row.id)}
      onMouseLeave={() => setHover(null)}
    >
      <span className="compare-fleettable__rank">{rank}</span>
      <Name row={row} onOpenProject={onOpenProject} />
      <ScoreDot score={row.score} axis={axis} fleetScore={fleetScore} />
      <span className={`compare-fleettable__num compare-fleettable__score ${scoreColorClass(row.score)}`}>{score1(row.score)}</span>
      <span className="compare-fleettable__num" title={row.delta == null ? t('compare.noRuns30d') : undefined}>
        {row.delta == null ? NONE : <CompareDeltaBadge delta={row.delta} />}
      </span>
      <span className="compare-fleettable__num">{nf(row.totalFiles ?? 0)}</span>
      {hasCoverage && (
        <span className={`compare-fleettable__num${caution(row.coveragePct != null && row.coveragePct < LOW_COVERAGE_PCT)}`}>
          {row.coveragePct == null ? NONE : pct(row.coveragePct)}
        </span>
      )}
      <span className="compare-fleettable__num">{fixed1(e.per100)}</span>
      <span className={`compare-fleettable__num${caution(e.critical > 0)}`}>{fixed1(e.criticalPerK)}</span>
      <span className={`compare-fleettable__num compare-fleettable__last${caution(row.stale)}`}>
        {relativeTime(row.lastISO) || NONE}
        {row.commitsSince > 0 && <span className="compare-fleettable__behind">{t('compare.behindShort', { count: nf(row.commitsSince) })}</span>}
      </span>
    </li>
  );
}

/* Projects without a score yet: computing, failed, or never evaluated. */
function PendingRows({ pending, unevaluated, errorsById, onOpenProject }) {
  return (
    <>
      {pending.map((row) => (
        <li key={row.id} className="compare-fleettable__pending">
          <Name row={row} onOpenProject={onOpenProject} />
          <span>{errorsById[row.id] ? t('compare.loadFailed') : t('compare.computing')}</span>
        </li>
      ))}
      {unevaluated.length > 0 && (
        <li className="compare-fleettable__pending">
          <span>{t('compare.noEvalsCollapsed', { count: unevaluated.length })}</span>
          <span>{unevaluated.map((r) => r.name).join(', ')}</span>
        </li>
      )}
    </>
  );
}

export default function CompareFleetTable({ scoredRows, pending, unevaluated, errorsById, fleetScore, hover, setHover, onOpenProject }) {
  const [sort, setSort] = useState({ key: FLEET_SORT.SCORE, desc: true });
  const axis = scoreAxisFor(scoredRows.map((r) => r.score));
  // Analysed-file counts are optional per project: no column when none report them.
  const hasCoverage = scoredRows.some((r) => r.coveragePct != null);
  const rowProps = { axis, fleetScore, hasCoverage, hover, setHover, onOpenProject };
  return (
    <ComparePanel ariaLabel={t('compare.fleetTableAria')} header={t('compare.fleetTableHeader', { count: scoredRows.length })} note={t('compare.fleetTableNote')}>
      <Head axis={axis} sort={sort} onSort={setSort} hasCoverage={hasCoverage} />
      <ol className="compare-fleettable">
        {sortFleet(scoredRows, sort.key, sort.desc).map((row, i) => <Row key={row.id} row={row} rank={i + 1} {...rowProps} />)}
        <PendingRows pending={pending} unevaluated={unevaluated} errorsById={errorsById} onOpenProject={onOpenProject} />
      </ol>
    </ComparePanel>
  );
}
