/**
 * CompareFleetView — the Compare tab's landing view, cut by information
 * priority (the "3a triage-first" design): scope-wide stat cards, the
 * needs-attention strip promoted to the top, a single-line projects table
 * with click-to-expand detail, and a compact dimensions board.
 *
 * Everything trimmed from the v2 table (severity split, sparkline,
 * coverage, per-dimension chips) lives inside a row's expansion; projects
 * that were never evaluated collapse into a single line.
 */
import { Fragment, useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { TermHeader, StatStrip, Stat, SectionLabel } from '../../../components/terminal/index.js';
import SevBadge from '../../../components/terminal/SevBadge.jsx';
import TrendBadge from '../../../components/TrendBadge.jsx';
import CompareTrendLine from './CompareTrendLine.jsx';
import CompareMatrix from './CompareMatrix.jsx';
import { relativeTime } from '../../../components/LastFetchedLine.jsx';
import { scoreColorClass, scoreGradeColorVar, complianceRatio } from '../../../utils/formatters.js';
import { scoreToGradeLabel } from '../../../utils/gradeThresholds.js';
import { t, LOCALE } from '../../../strings/index.js';
import { consequenceOf, consequenceLevel } from '../compareModel.js';

const nf = (n) => (n == null ? '—' : Number(n).toLocaleString(LOCALE));
const score1 = (s) => (s == null ? '—' : (Math.round(s * 10) / 10).toFixed(1));

function levelLabel(level) {
  return t(`compare.level${level.charAt(0).toUpperCase()}${level.slice(1)}`);
}

function ScopePicker({
  rows, scopeIds, toggleProject, selectAll, selectFlagged, pickerOpen, setPickerOpen, scopeCount,
}) {
  // Dismiss like every other popover in the app (NavBreadcrumb's pattern):
  // a press anywhere outside, or Escape, closes it.
  const rootRef = useRef(null);
  useEffect(() => {
    if (!pickerOpen) return undefined;
    const onDown = (e) => { if (!rootRef.current?.contains(e.target)) setPickerOpen(false); };
    const onEsc = (e) => { if (e.key === 'Escape') setPickerOpen(false); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onEsc);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onEsc);
    };
  }, [pickerOpen, setPickerOpen]);

  const allSelected = scopeIds == null || scopeCount === rows.length;
  const label = allSelected
    ? t('compare.scopeAll', { count: rows.length })
    : t('compare.scopeSome', { selected: scopeCount, count: rows.length });
  return (
    <span className="compare-picker" ref={rootRef}>
      <button
        type="button"
        className={`compare-picker__toggle${allSelected ? '' : ' compare-picker__toggle--filtered'}`}
        onClick={() => setPickerOpen(!pickerOpen)}
        aria-expanded={pickerOpen}
      >
        {label}
        <span className="compare-picker__glyph" aria-hidden="true">{pickerOpen ? '▲' : '▼'}</span>
      </button>
      {pickerOpen && (
        <div className="compare-picker__pop">
          <div className="compare-picker__head">
            <span className="compare-picker__title">{t('compare.pickerTitle')}</span>
            <button type="button" className="compare-picker__quick" onClick={selectAll}>
              {t('compare.pickerAll')}
            </button>
            <button type="button" className="compare-picker__quick" onClick={selectFlagged}>
              {t('compare.pickerFlagged')}
            </button>
          </div>
          <ul className="compare-picker__list">
            {rows.map((row) => {
              const on = scopeIds == null || scopeIds.includes(row.id);
              return (
                <li key={row.id}>
                  <label className="compare-picker__row">
                    <input
                      type="checkbox"
                      checked={on}
                      onChange={() => toggleProject(row.id)}
                    />
                    <span className="compare-picker__name">
                      {row.name}
                      {row.remote && <span className="compare-row__remote">{t('compare.remoteTag')}</span>}
                    </span>
                    <span
                      className={`compare-picker__score ${scoreColorClass(row.score)}`}
                    >
                      {score1(row.score)}
                    </span>
                    <span className="compare-picker__viol">
                      {row.hasData ? t('compare.violCount', { count: nf(row.totalViolations) }) : '—'}
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </span>
  );
}

/* Duel trigger — the header launcher's two-pick flow: the first pick pins
   side A (shown as a removable chip in the side-A identity color), the
   second navigates to the duel — choosing is the action, no confirm step.
   With the scope at exactly two projects it skips the popover entirely and
   duels them directly. The menu renders through a PORTAL at a fixed
   position: the header sits over overflow containers that would clip an
   in-flow popover, and it flips upward when the space below cannot fit
   it. */
const DUEL_MENU_MAX_H = 260; // keep in sync with the CSS max-height

function DuelTrigger({ targets, onStart, openDirect = null }) {
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(null);
  const [pos, setPos] = useState(null);
  const btnRef = useRef(null);
  const menuRef = useRef(null);

  const list = targets.filter((other) => other.id !== pinned?.id);

  const close = () => { setOpen(false); setPinned(null); };

  const toggle = () => {
    if (open) { close(); return; }
    // Exactly-two scope: nothing to pick, duel them directly.
    if (openDirect) { openDirect(); return; }
    const r = btnRef.current?.getBoundingClientRect();
    if (!r) return;
    const spaceBelow = window.innerHeight - r.bottom;
    const openUp = spaceBelow < DUEL_MENU_MAX_H + 12 && r.top > spaceBelow;
    setPos({
      left: Math.max(8, Math.min(r.left, window.innerWidth - 228)),
      ...(openUp
        ? { bottom: window.innerHeight - r.top + 6 }
        : { top: r.bottom + 6 }),
    });
    setOpen(true);
  };

  const pick = (other) => {
    if (!pinned) { setPinned(other); return; }
    const a = pinned.id;
    close();
    onStart(a, other.id);
  };

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => {
      if (!btnRef.current?.contains(e.target) && !menuRef.current?.contains(e.target)) close();
    };
    const onEsc = (e) => { if (e.key === 'Escape') close(); };
    // Any OUTSIDE scroll moved the anchor, so the menu must go — but the
    // menu's own list scrolls too (capture sees those events as well), and
    // scrolling the options must not dismiss them.
    const onAnchorMoved = (e) => {
      if (menuRef.current && e.target instanceof Node && menuRef.current.contains(e.target)) return;
      close();
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onEsc);
    window.addEventListener('scroll', onAnchorMoved, true);
    window.addEventListener('resize', onAnchorMoved);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onEsc);
      window.removeEventListener('scroll', onAnchorMoved, true);
      window.removeEventListener('resize', onAnchorMoved);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  return (
    <span className="compare-dueltrigger" onClick={(e) => e.stopPropagation()}>
      <button
        ref={btnRef}
        type="button"
        className="compare-dueltrigger__btn compare-dueltrigger__btn--launcher"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t('compare.duelLaunchAria')}
        onClick={toggle}
      >
        {t('compare.duelOpen')} {open ? '▾' : '▸'}
      </button>
      {open && pos && createPortal(
        <span className="compare-dueltrigger__menu" role="menu" ref={menuRef} style={pos}>
          {!pinned && (
            <span className="compare-dueltrigger__hint">{t('compare.duelPickA')}</span>
          )}
          {pinned && (
            <span className="compare-dueltrigger__pin">
              <span className="compare-dueltrigger__pinName">{pinned.name}</span>
              <span className={`compare-dueltrigger__itemScore ${scoreColorClass(pinned.score)}`}>
                {score1(pinned.score)}
              </span>
              <button
                type="button"
                className="compare-dueltrigger__unpin"
                aria-label={t('compare.duelUnpin')}
                onClick={() => setPinned(null)}
              >
                ×
              </button>
            </span>
          )}
          {list.map((other) => (
            <button
              key={other.id}
              type="button"
              role="menuitem"
              className="compare-dueltrigger__item"
              onClick={() => pick(other)}
            >
              <span>
                {other.name}
                {other.remote && <span className="compare-row__remote">{t('compare.remoteTag')}</span>}
              </span>
              <span className={`compare-dueltrigger__itemScore ${scoreColorClass(other.score)}`}>
                {score1(other.score)}
              </span>
            </button>
          ))}
        </span>,
        document.body,
      )}
    </span>
  );
}

/* One line per project — the row IS the summary now: identity, score,
   30-day spark + delta, violations split by severity, freshness with
   commits-behind. The score matrix below already carries every
   per-dimension number, so the old expansion (chips, facts, per-row duel)
   had nothing left to say; the name opens the project, the same gesture as
   every other list on this screen, and the header duel button covers
   head-to-heads. */
function ProjectRow({ row, rank, onOpenProject, error }) {
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
              <span className="compare-row__sev">
                <SevBadge level="critical" format="count-abbr" count={row.severity.critical} />
                <SevBadge level="major" format="count-abbr" count={row.severity.major} />
                <SevBadge level="minor" format="count-abbr" count={row.severity.minor} />
              </span>
              <span className="compare-row__violTotal">{nf(row.totalViolations)}</span>
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

export default function CompareFleetView({
  rows, orderedRows, fleet, board, attention, errorsById,
  sortDir, toggleSortDir, pickerOpen, setPickerOpen, scopeIds, scopeCount,
  toggleProject, selectAll, selectFlagged, openDimension, openDuel, openDuelPair, onOpenProject,
  onOpenProjectDimension,
}) {
  // The score matrix shows the same projects as the ranked table, in the
  // same order — never-evaluated rows have no numbers to grid.
  const scoredRows = orderedRows.filter((r) => r.hasData);
  const [showUnevaluated, setShowUnevaluated] = useState(false);
  // The strip always leads with the top 3 by consequence (even a healthy
  // fleet has a "most consequential" trio). Beyond those, only rows that
  // actually flag ('watch' and up) hide behind the expand toggle — a clear
  // row past rank 3 is not "needs attention".
  const [attnOpen, setAttnOpen] = useState(false);
  const attnAll = [
    ...attention.slice(0, 3),
    ...attention.slice(3).filter((a) => a.level !== 'clear'),
  ];
  const attnShown = attnOpen ? attnAll : attnAll.slice(0, 3);

  // Never-evaluated projects (settled, no data, no error) collapse into one
  // line; pending and errored rows stay visible individually.
  const isUnevaluated = (row) => row.loaded && !row.hasData && !errorsById[row.id];
  const mainRows = orderedRows.filter((row) => !isUnevaluated(row));
  const unevaluated = orderedRows.filter(isUnevaluated);

  return (
    <>
      <div className="compare-page__top">
        <TermHeader
          name={t('compare.title')}
          sub={t('compare.subtitle', {
            count: scopeCount,
            files: nf(fleet.totalFiles),
          })}
        />
        <div className="compare-header__controls">
          {openDuelPair && scoredRows.length >= 2 && (
            <DuelTrigger
              targets={scoredRows}
              onStart={openDuelPair}
              openDirect={openDuel}
            />
          )}
          <span className="compare-sort" role="group" aria-label={t('compare.sortAria')}>
            <button
              type="button"
              className="compare-sort__btn compare-sort__btn--on"
              onClick={toggleSortDir}
              aria-label={t('compare.sortToggleAria')}
            >
              {t('compare.sortScore')} {sortDir === 'desc' ? '↓' : '↑'}
            </button>
          </span>
          <ScopePicker
            rows={rows}
            scopeIds={scopeIds}
            scopeCount={scopeCount}
            toggleProject={toggleProject}
            selectAll={selectAll}
            selectFlagged={selectFlagged}
            pickerOpen={pickerOpen}
            setPickerOpen={setPickerOpen}
          />
        </div>
      </div>

      <StatStrip cards>
        <Stat
          label={t('compare.cardScopeScore')}
          value={score1(fleet.score)}
          hint={fleet.score != null
            ? `${scoreToGradeLabel(fleet.score) || ''} · ${t('compare.projectsInScope', { count: fleet.scoredCount })}`
            : t('compare.noScores')}
          trailing={<TrendBadge delta={fleet.delta} />}
        />
        <Stat
          label={t('compare.cardViolations')}
          value={nf(fleet.totalViolations)}
          hint={(
            <span className="compare-card__sev">
              <SevBadge level="critical" count={fleet.severity.critical} />
              <SevBadge level="major" count={fleet.severity.major} />
              <SevBadge level="minor" count={fleet.severity.minor} />
            </span>
          )}
        />
        <Stat
          label={t('compare.cardCompliance')}
          value={fleet.passPct != null ? `${fleet.passPct}%` : '—'}
          hint={t('compare.passingChecks', {
            pass: nf(fleet.totalCompliance),
            checks: nf(fleet.checks),
          })}
        />
        <Stat
          label={t('compare.cardSpread')}
          value={fleet.spread != null ? score1(fleet.spread) : '—'}
          hint={fleet.lead && fleet.trail
            ? t('compare.spreadNote', {
              lead: fleet.lead.name,
              leadScore: score1(fleet.lead.score),
              trail: fleet.trail.name,
              trailScore: score1(fleet.trail.score),
            })
            : t('compare.needTwo')}
        />
      </StatStrip>

      {/* The actionable summary reads first: a slim strip, not a side panel. */}
      {attention.length > 0 && (
        <section className="compare-panel" aria-label={t('compare.attentionAria')}>
          <div className="compare-panel__head">
            <SectionLabel>{t('compare.attentionHeader', { count: attnAll.length })}</SectionLabel>
            <span className="compare-panel__note">{t('compare.attentionNote')}</span>
            {attnAll.length > 3 && (
              <button
                type="button"
                className="compare-attention__toggle"
                onClick={() => setAttnOpen((v) => !v)}
              >
                {attnOpen
                  ? `${t('compare.attentionLess')} ▾`
                  : `${t('compare.attentionMore', { count: attnAll.length - 3 })} ▸`}
              </button>
            )}
          </div>
          <div className="compare-attention compare-attention--strip">
            {attnShown.map(({ row, level, reasons, worstDim }, i) => (
              <Fragment key={row.id}>
                {/* The standards list draws this same boundary: the always-on
                    trio above the line, the expanded rest dimmed below it. */}
                {i === 3 && <div className="compare-attention__divider" aria-hidden="true" />}
              <div
                className={`compare-attention__item compare-attention__item--${level}${i >= 3 ? ' compare-attention__item--rest' : ''}`}
                style={{ '--attention-accent': scoreGradeColorVar(row.score) }}
              >
                <div className="compare-attention__top">
                  <button
                    type="button"
                    className="compare-attention__name"
                    onClick={() => onOpenProject(row.id)}
                  >
                    {row.name}
                  </button>
                  <span className={`compare-attention__level compare-attention__level--${level}`}>
                    {levelLabel(level)}
                  </span>
                </div>
                <p className="compare-attention__why">
                  {reasons.map((r) => {
                    if (r.type === 'worstDim') return t('compare.reasonWorstDim', { dim: r.dim, score: score1(r.score) });
                    if (r.type === 'declining') return t('compare.reasonDeclining', { delta: r.delta });
                    if (r.type === 'stale') {
                      return r.commits != null
                        ? t('compare.reasonStaleCommits', { count: nf(r.commits) })
                        : t('compare.reasonStale');
                    }
                    if (r.type === 'coverage') return t('compare.reasonCoverage', { pct: r.pct });
                    return null;
                  }).filter(Boolean).join(' · ')}
                  {worstDim && (
                    <button
                      type="button"
                      className="compare-attention__link"
                      onClick={() => openDimension(worstDim)}
                    >
                      {t('compare.openDimension', { dim: worstDim })} ›
                    </button>
                  )}
                </p>
              </div>
              </Fragment>
            ))}
          </div>
        </section>
      )}

      {/* v4a: every score at a glance, right after the ranked table.
          Column headers SORT (the dimensions board below still drills); a
          cell opens that project's own dimension (remote rows open the
          shared project). */}
      <CompareMatrix
        ariaLabel={t('compare.matrixAria')}
        header={t('compare.matrixHeader', { rows: scoredRows.length, cols: board.length })}
        note={t('compare.matrixNote')}
        footOverall={fleet.score}
        columns={board.map((b) => ({ key: b.key, label: b.label, avg: b.avg }))}
        matrixRows={scoredRows.map((row) => ({
          id: row.id,
          name: row.name,
          remote: row.remote,
          overall: row.score,
          onOpenRow: () => onOpenProject(row.id),
          cells: Object.fromEntries(row.dims.map((dim) => [dim.key, {
            score: dim.score,
            title: t('compare.openDimensionIn', { dim: dim.label, project: row.name }),
            onClick: () => (row.remote || !dim.fromRunId || !onOpenProjectDimension
              ? onOpenProject(row.id)
              : onOpenProjectDimension({ id: row.id, source: row.source, runId: dim.fromRunId, dimName: dim.name, dateLabel: dim.fromDateLabel })),
          }])),
        }))}
      />

      <section className="compare-panel" aria-label={t('compare.dimensionsAria')}>
        <div className="compare-panel__head">
          <SectionLabel>{t('compare.dimensionsHeader', { count: board.length })}</SectionLabel>
          <span className="compare-panel__note">{t('compare.dimensionsNote')}</span>
        </div>
        <ul className="compare-board compare-board--grid">
          {board.map((b) => (
            <li key={b.key}>
              <button type="button" className="compare-board__row" onClick={() => openDimension(b.key)}>
                <span className="compare-board__label">{b.label}</span>
                <span className={`compare-board__score ${scoreColorClass(b.avg)}`}>{score1(b.avg)}</span>
                <span className="compare-board__delta"><TrendBadge delta={b.delta} /></span>
                <span className="compare-board__viol">{t('compare.violCount', { count: nf(b.violations) })}</span>
                <span className="compare-board__chevron" aria-hidden="true">›</span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section className="compare-panel" aria-label={t('compare.projectsAria')}>
        <div className="compare-panel__head">
          <SectionLabel>{t('compare.projectsHeader', { count: scopeCount })}</SectionLabel>
          <span className="compare-panel__note">
            {sortDir === 'desc' ? t('compare.sortNoteScore') : t('compare.sortNoteScoreAsc')}
            {' · '}
            {t('compare.rowOpenHint')}
          </span>
        </div>
        <div className="compare-table" role="table">
          <div className="compare-row compare-row--head" role="row">
            <span className="compare-row__stripe" />
            <span className="compare-row__rank" />
            <span className="compare-row__project">{t('compare.colProject')}</span>
            <span className="compare-row__score">{t('compare.colScore')}</span>
            <span className="compare-row__trend">{t('compare.colDelta')}</span>
            <span className="compare-row__viol">{t('compare.colViolations')}</span>
            <span className="compare-row__ratio">{t('compare.colRatio')}</span>
            <span className="compare-row__last">{t('compare.colLast')}</span>
          </div>
          {mainRows.map((row, i) => (
            <ProjectRow
              key={row.id}
              row={row}
              rank={i + 1}
              onOpenProject={onOpenProject}
              error={errorsById[row.id]}
            />
          ))}
          {unevaluated.length > 0 && (
            <div className="compare-noevals">
              <button
                type="button"
                className="compare-noevals__toggle"
                aria-expanded={showUnevaluated}
                onClick={() => setShowUnevaluated((v) => !v)}
              >
                <span className="compare-noevals__dot" aria-hidden="true">·</span>
                {t('compare.noEvalsCollapsed', { count: unevaluated.length })}
                <span className="compare-noevals__action">
                  {showUnevaluated ? t('compare.hideAction') : t('compare.showAction')} {showUnevaluated ? '▾' : '▸'}
                </span>
              </button>
              {showUnevaluated && unevaluated.map((row) => (
                <div key={row.id} className="compare-noevals__row">
                  <span className="compare-row__rank" />
                  <span className="compare-row__name">{row.name}</span>
                  {row.lang && <span className="compare-row__meta">{row.lang}</span>}
                  <span className="compare-noevals__note">{t('compare.noRuns')}</span>
                </div>
              ))}
            </div>
          )}
          {fleet.scoredCount > 1 && (
            <div className="compare-row compare-row--foot" role="row" aria-label={t('compare.scopeAverage')}>
              <span className="compare-row__stripe" />
              <span className="compare-row__rank" />
              <span className="compare-row__project compare-row__footLabel">{t('compare.scopeAverage')}</span>
              <span className={`compare-row__score ${scoreColorClass(fleet.score)}`}>{score1(fleet.score)}</span>
              <span className="compare-row__trend"><TrendBadge delta={fleet.delta} /></span>
              <span className="compare-row__viol">
                <span className="compare-row__sev">
                  <SevBadge level="critical" format="count-abbr" count={fleet.severity.critical} />
                  <SevBadge level="major" format="count-abbr" count={fleet.severity.major} />
                  <SevBadge level="minor" format="count-abbr" count={fleet.severity.minor} />
                </span>
                <span className="compare-row__violTotal">{nf(fleet.totalViolations)}</span>
              </span>
              <span className="compare-row__ratio">{complianceRatio(fleet.totalViolations, fleet.totalCompliance)}</span>
              <span className="compare-row__last" />
            </div>
          )}
        </div>
      </section>
    </>
  );
}
