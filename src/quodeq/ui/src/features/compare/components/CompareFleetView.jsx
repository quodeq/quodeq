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
import CompareMatrix from './CompareMatrix.jsx';
import { t, LOCALE } from '../../../strings/index.js';
import CompareFleetHeader from './CompareFleetHeader.jsx';
import CompareFleetStatCards from './CompareFleetStatCards.jsx';
import CompareAttentionStrip from './CompareAttentionStrip.jsx';
import CompareDimensionsBoard from './CompareDimensionsBoard.jsx';
import CompareProjectsTable from './CompareProjectsTable.jsx';

const nf = (n) => (n == null ? '—' : Number(n).toLocaleString(LOCALE));
const score1 = (s) => (s == null ? '—' : (Math.round(s * 10) / 10).toFixed(1));

function buildAttentionItems(attnAll, onOpenProject, openDimension) {
  return attnAll.map(({ row, level, reasons, worstDim }) => ({
    key: row.id,
    level,
    accentScore: row.score,
    name: row.name,
    onNameClick: () => onOpenProject(row.id),
    why: reasons.map((r) => {
      if (r.type === 'worstDim') return t('compare.reasonWorstDim', { dim: r.dim, score: score1(r.score) });
      if (r.type === 'declining') return t('compare.reasonDeclining', { delta: r.delta });
      if (r.type === 'stale') {
        return r.commits != null
          ? t('compare.reasonStaleCommits', { count: nf(r.commits) })
          : t('compare.reasonStale');
      }
      if (r.type === 'coverage') return t('compare.reasonCoverage', { pct: r.pct });
      return null;
    }).filter(Boolean).join(' · '),
    extra: worstDim && (
      <button
        type="button"
        className="compare-attention__link"
        onClick={() => openDimension(worstDim)}
      >
        {t('compare.openDimension', { dim: worstDim })} ›
      </button>
    ),
  }));
}

function buildFleetMatrixRows(scoredRows, onOpenProject, onOpenProjectDimension) {
  return scoredRows.map((row) => ({
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
  }));
}

/**
 * Row partitioning shared by the render below:
 *   - scoredRows: what the score matrix grids (never-evaluated rows have no
 *     numbers to show).
 *   - attnAll: the attention strip's full list — top 3 by consequence
 *     always show (even a healthy fleet has a "most consequential" trio),
 *     beyond that only rows that actually flag ('watch'+) qualify.
 *   - mainRows / unevaluated: never-evaluated projects (settled, no data,
 *     no error) collapse into one line; pending/errored rows stay
 *     individually visible.
 */
function partitionFleetRows(orderedRows, attention, errorsById) {
  const scoredRows = orderedRows.filter((r) => r.hasData);
  const attnAll = [
    ...attention.slice(0, 3),
    ...attention.slice(3).filter((a) => a.level !== 'clear'),
  ];
  const isUnevaluated = (row) => row.loaded && !row.hasData && !errorsById[row.id];
  const mainRows = orderedRows.filter((row) => !isUnevaluated(row));
  const unevaluated = orderedRows.filter(isUnevaluated);
  return { scoredRows, attnAll, mainRows, unevaluated };
}

export default function CompareFleetView({
  rows, orderedRows, fleet, board, attention, errorsById,
  sortDir, toggleSortDir, pickerOpen, setPickerOpen, scopeIds, scopeCount,
  toggleProject, selectAll, selectFlagged, openDimension, openDuel, openDuelPair, onOpenProject,
  onOpenProjectDimension,
}) {
  const { scoredRows, attnAll, mainRows, unevaluated } = partitionFleetRows(orderedRows, attention, errorsById);

  return (
    <>
      <CompareFleetHeader
        scopeCount={scopeCount} totalFiles={fleet.totalFiles} scoredRows={scoredRows}
        openDuelPair={openDuelPair} openDuel={openDuel} board={board} openDimension={openDimension}
        sortDir={sortDir} toggleSortDir={toggleSortDir} rows={rows} scopeIds={scopeIds}
        toggleProject={toggleProject} selectAll={selectAll} selectFlagged={selectFlagged}
        pickerOpen={pickerOpen} setPickerOpen={setPickerOpen}
      />

      <CompareFleetStatCards fleet={fleet} />
      {/* The actionable summary reads first: a slim strip, not a side panel. */}
      <CompareAttentionStrip
        ariaLabel={t('compare.attentionAria')}
        noteText={t('compare.attentionNote')}
        items={buildAttentionItems(attnAll, onOpenProject, openDimension)}
      />
      {/* v4a: every score at a glance — column headers SORT, a cell opens
          that project's own dimension (remote rows open the shared project). */}
      <CompareMatrix
        ariaLabel={t('compare.matrixAria')}
        header={t('compare.matrixHeader', { rows: scoredRows.length, cols: board.length })}
        note={t('compare.matrixNote')}
        footOverall={fleet.score}
        columns={board.map((b) => ({ key: b.key, label: b.label, avg: b.avg }))}
        matrixRows={buildFleetMatrixRows(scoredRows, onOpenProject, onOpenProjectDimension)}
      />

      <CompareDimensionsBoard board={board} openDimension={openDimension} />

      <CompareProjectsTable
        mainRows={mainRows}
        unevaluated={unevaluated}
        fleet={fleet}
        sortDir={sortDir}
        scopeCount={scopeCount}
        onOpenProject={onOpenProject}
        errorsById={errorsById}
      />
    </>
  );
}
