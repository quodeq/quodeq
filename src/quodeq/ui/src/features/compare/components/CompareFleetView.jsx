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
import { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { TermHeader, StatStrip, Stat, SectionLabel } from '../../../components/terminal/index.js';
import SevBadge from '../../../components/terminal/SevBadge.jsx';
import TrendBadge from '../../../components/TrendBadge.jsx';
import CompareTrendLine from './CompareTrendLine.jsx';
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

/* Duel trigger: a button opening a small opponent menu. Choosing navigates
   to the head-to-head, so this is an action menu, not a value-holding
   select. The menu renders through a PORTAL at a fixed position: the
   projects table is an overflow container, and an in-flow popover gets
   clipped at its edge for rows near the bottom. It flips upward when the
   space below the button cannot fit it, and any scroll or resize
   dismisses it (the anchor moved). */
const DUEL_MENU_MAX_H = 260; // keep in sync with the CSS max-height

function DuelTrigger({ row, targets, onPick }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState(null);
  const btnRef = useRef(null);
  const menuRef = useRef(null);

  const toggle = () => {
    if (open) { setOpen(false); return; }
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

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => {
      if (!btnRef.current?.contains(e.target) && !menuRef.current?.contains(e.target)) setOpen(false);
    };
    const onEsc = (e) => { if (e.key === 'Escape') setOpen(false); };
    // Any OUTSIDE scroll moved the anchor, so the menu must go — but the
    // menu's own list scrolls too (capture sees those events as well), and
    // scrolling the options must not dismiss them.
    const onAnchorMoved = (e) => {
      if (menuRef.current && e.target instanceof Node && menuRef.current.contains(e.target)) return;
      setOpen(false);
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
  }, [open]);
  return (
    <span className="compare-dueltrigger" onClick={(e) => e.stopPropagation()}>
      <button
        ref={btnRef}
        type="button"
        className="compare-dueltrigger__btn"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t('compare.duelWithAria', { project: row.name })}
        onClick={toggle}
      >
        {t('compare.duelOpen')} {open ? '▾' : '▸'}
      </button>
      {open && pos && createPortal(
        <span className="compare-dueltrigger__menu" role="menu" ref={menuRef} style={pos}>
          {targets.map((other) => (
            <button
              key={other.id}
              type="button"
              role="menuitem"
              className="compare-dueltrigger__item"
              onClick={() => { setOpen(false); onPick(other.id); }}
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

/* Detail-on-demand block under an expanded row: everything the single-line
   row no longer carries. */
function RowDetail({ row, duelTargets, openDimension, onOpenProject, openDuelPair }) {
  return (
    <div className="compare-rowdetail">
      <div className="compare-rowdetail__facts">
        <span className="compare-row__sev">
          <SevBadge level="critical" format="count-abbr" count={row.severity.critical} />
          <SevBadge level="major" format="count-abbr" count={row.severity.major} />
          <SevBadge level="minor" format="count-abbr" count={row.severity.minor} />
        </span>
        {row.spark.length > 1 && (
          <CompareTrendLine scores={row.spark} />
        )}
        {row.coveragePct != null && (
          <span className={row.coveragePct < 80 ? 'compare-row__cov--low' : undefined}>
            {t('compare.analyzedPct', { pct: row.coveragePct })}
          </span>
        )}
        {row.totalFiles != null && (
          <span>{t('compare.filesSuffix', { count: nf(row.totalFiles) })}</span>
        )}
        {row.commitsSince != null && row.commitsSince > 0 && (
          <span className="compare-rowdetail__stale">
            {t('compare.commitsSince', { count: nf(row.commitsSince) })}
          </span>
        )}
      </div>
      <div className="compare-rowdetail__dims">
        {row.dims.filter((d) => d.score != null).map((dim) => (
          <button
            key={dim.key}
            type="button"
            className="compare-dim-chip compare-dim-chip--inline"
            title={t('compare.openDimension', { dim: dim.label })}
            onClick={(e) => { e.stopPropagation(); openDimension(dim.key); }}
          >
            <span className={scoreColorClass(dim.score)}>{score1(dim.score)}</span>
            <span className="compare-dim-chip__label">{dim.label}</span>
          </button>
        ))}
      </div>
      <div className="compare-rowdetail__actions">
        <button
          type="button"
          className="compare-rowdetail__open"
          onClick={(e) => { e.stopPropagation(); onOpenProject(row.id); }}
        >
          {t('compare.openProject')} ›
        </button>
        {openDuelPair && duelTargets.length > 0 && (
          <DuelTrigger
            row={row}
            targets={duelTargets}
            onPick={(otherId) => openDuelPair(row.id, otherId)}
          />
        )}
      </div>
    </div>
  );
}

function ProjectRow({ row, rank, expanded, onToggle, onOpenProject, openDimension, error, duelTargets, openDuelPair }) {
  const level = consequenceLevel(consequenceOf(row));
  return (
    <div
      className={`compare-rowgroup compare-rowgroup--${level}${expanded ? ' compare-rowgroup--open' : ''}`}
      // The stripe's colour is the project's GRADE; the consequence level
      // only decides whether a stripe shows.
      style={row.hasData ? { '--row-accent': scoreGradeColorVar(row.score) } : undefined}
    >
      <div
        className={`compare-row${row.hasData ? '' : ' compare-row--nodata'}`}
        role="row"
        tabIndex={0}
        aria-expanded={row.hasData ? expanded : undefined}
        onClick={() => (row.hasData ? onToggle(row.id) : undefined)}
        onKeyDown={(e) => { if (e.key === 'Enter' && row.hasData) onToggle(row.id); }}
      >
        <span className="compare-row__stripe" aria-hidden="true" />
        <span className="compare-row__rank">{rank}</span>
        <span className="compare-row__project">
          <span className="compare-row__name">{row.name}</span>
          {row.lang && <span className="compare-row__meta">{row.lang}</span>}
          {row.remote && <span className="compare-row__remote">{t('compare.remoteTag')}</span>}
        </span>
        {row.hasData ? (
          <>
            <span className="compare-row__score">
              <span className={scoreColorClass(row.score)}>{score1(row.score)}</span>
              <span className="compare-row__tier">{scoreToGradeLabel(row.score) || ''}</span>
            </span>
            <span className="compare-row__delta">
              {row.delta != null ? (
                <TrendBadge delta={row.delta} />
              ) : row.lastDelta != null ? (
                <span className="compare-delta--old" title={t('compare.oldDeltaTip')}>
                  <TrendBadge delta={row.lastDelta} />
                </span>
              ) : null}
            </span>
            <span className="compare-row__viol">{nf(row.totalViolations)}</span>
            <span
              className="compare-row__ratio"
              title={t('compare.ratioTip', { pass: nf(row.totalCompliance), checks: nf(row.totalCompliance + row.totalViolations) })}
            >
              {complianceRatio(row.totalViolations, row.totalCompliance)}
            </span>
            <span
              className={`compare-row__last${row.stale ? ' compare-row__last--stale' : ''}`}
              title={row.commitsSince != null && row.commitsSince > 0
                ? t('compare.commitsSince', { count: nf(row.commitsSince) })
                : undefined}
            >
              {relativeTime(row.lastISO) || '—'}
            </span>
            <span className="compare-row__chev" aria-hidden="true">{expanded ? '▾' : '▸'}</span>
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
      {expanded && row.hasData && (
        <RowDetail
          row={row}
          duelTargets={duelTargets}
          openDimension={openDimension}
          onOpenProject={onOpenProject}
          openDuelPair={openDuelPair}
        />
      )}
    </div>
  );
}

export default function CompareFleetView({
  rows, orderedRows, fleet, board, attention, errorsById,
  sortDir, toggleSortDir, pickerOpen, setPickerOpen, scopeIds, scopeCount,
  toggleProject, selectAll, selectFlagged, openDimension, openDuel, openDuelPair, onOpenProject,
}) {
  // Any number of rows can hold their detail open at once — comparing two
  // projects' expansions side by side is the point of this screen.
  const [expandedIds, setExpandedIds] = useState(() => new Set());
  const [showUnevaluated, setShowUnevaluated] = useState(false);
  const toggleRow = (id) => setExpandedIds((cur) => {
    const next = new Set(cur);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  });

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
          {openDuel && (
            <button type="button" className="compare-duel-cta" onClick={openDuel}>
              {t('compare.duelAction')}
            </button>
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
            <SectionLabel>{t('compare.attentionHeader', { count: attention.length })}</SectionLabel>
            <span className="compare-panel__note">{t('compare.attentionNote')}</span>
          </div>
          <div className="compare-attention compare-attention--strip">
            {attention.map(({ row, level, reasons, worstDim }) => (
              <div
                key={row.id}
                className={`compare-attention__item compare-attention__item--${level}`}
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
            ))}
          </div>
        </section>
      )}

      <section className="compare-panel" aria-label={t('compare.projectsAria')}>
        <div className="compare-panel__head">
          <SectionLabel>{t('compare.projectsHeader', { count: scopeCount })}</SectionLabel>
          <span className="compare-panel__note">
            {sortDir === 'desc' ? t('compare.sortNoteScore') : t('compare.sortNoteScoreAsc')}
            {' · '}
            {t('compare.rowExpandHint')}
          </span>
        </div>
        <div className="compare-table" role="table">
          <div className="compare-row compare-row--head" role="row">
            <span className="compare-row__stripe" />
            <span className="compare-row__rank" />
            <span className="compare-row__project">{t('compare.colProject')}</span>
            <span className="compare-row__score">{t('compare.colScore')}</span>
            <span className="compare-row__delta">{t('compare.colDelta')}</span>
            <span className="compare-row__viol">{t('compare.colViolations')}</span>
            <span className="compare-row__ratio">{t('compare.colRatio')}</span>
            <span className="compare-row__last">{t('compare.colLast')}</span>
            <span className="compare-row__chev" />
          </div>
          {mainRows.map((row, i) => (
            <ProjectRow
              key={row.id}
              row={row}
              rank={i + 1}
              expanded={expandedIds.has(row.id)}
              onToggle={toggleRow}
              onOpenProject={onOpenProject}
              openDimension={openDimension}
              error={errorsById[row.id]}
              duelTargets={rows.filter((r) => r.hasData && r.id !== row.id)}
              openDuelPair={openDuelPair}
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
              <span className="compare-row__delta"><TrendBadge delta={fleet.delta} /></span>
              <span className="compare-row__viol">{nf(fleet.totalViolations)}</span>
              <span className="compare-row__ratio">{complianceRatio(fleet.totalViolations, fleet.totalCompliance)}</span>
              <span className="compare-row__last" />
              <span className="compare-row__chev" />
            </div>
          )}
        </div>
      </section>

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
    </>
  );
}
