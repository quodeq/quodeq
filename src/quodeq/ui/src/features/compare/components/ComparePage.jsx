/**
 * ComparePage — fleet-wide comparison of every local project.
 *
 * Two views, both driven by the same per-project compare summaries:
 *   fleet     — ranked projects table, per-dimension board, attention list.
 *   dimension — one dimension across the scope: standings, principles radar,
 *               principle cards. Reached by clicking any dimension chip.
 *
 * Data arrives progressively (one query per project — see useCompareData);
 * rows for projects still computing render as pending instead of blocking
 * the whole screen.
 */
import { useMemo, useState, useCallback, useEffect, useRef } from 'react';
import EmptyState from '../../../components/EmptyState.jsx';
import { t } from '../../../strings/index.js';
import { useCompareData } from '../hooks/useCompareData.js';
import {
  buildRow, buildFleet, buildDimensionsBoard, buildAttention,
  buildDimensionView, sortRows, consequenceOf, consequenceLevel,
} from '../compareModel.js';
import CompareFleetView from './CompareFleetView.jsx';
import CompareDimensionView from './CompareDimensionView.jsx';

const SCOPE_STORAGE_KEY = 'quodeq.compare.scope';

function readStoredScope() {
  try {
    const raw = localStorage.getItem(SCOPE_STORAGE_KEY);
    const ids = raw ? JSON.parse(raw) : null;
    return Array.isArray(ids) ? ids : null;
  } catch {
    return null;
  }
}

function storeScope(ids) {
  try {
    if (ids == null) localStorage.removeItem(SCOPE_STORAGE_KEY);
    else localStorage.setItem(SCOPE_STORAGE_KEY, JSON.stringify(ids));
  } catch {
    /* storage unavailable — scope just won't persist */
  }
}

export default function ComparePage({
  projects, projectsLoaded, onOpenProject,
  /* Navigation contract: the dimension drill-down is a nav-stack entry, not
     component state — `dimension` arrives as a route param, drilling in
     pushes (browser back returns to the fleet), switching dimensions
     replaces, and the back control pops. */
  dimension = null,
  onOpenDimension,
  onSwitchDimension,
  onBack,
}) {
  const localProjects = useMemo(
    () => (projects || []).filter((p) => p && (p.id || p.name)),
    [projects],
  );
  const { summariesById, errorsById } = useCompareData(localProjects);

  const view = dimension || 'fleet';
  // Score is the only table ordering (consequence ranked near-inverse of it
  // on real fleets); the toggle flips best-first / worst-first.
  const [sortDir, setSortDir] = useState('desc');
  const [pickerOpen, setPickerOpen] = useState(false);
  // null scope = everything (including projects added later); an array is an
  // explicit selection.
  const [scopeIds, setScopeIds] = useState(readStoredScope);

  // One timestamp per mount: staleness/delta windows don't need to tick.
  const now = useMemo(() => new Date().toISOString(), []);

  const rows = useMemo(
    () => localProjects.map((p) => buildRow(p, summariesById[p.id || p.name], now)),
    [localProjects, summariesById, now],
  );

  const scopeSet = scopeIds == null ? null : new Set(scopeIds);
  const scopeRows = useMemo(
    () => (scopeSet && scopeSet.size ? rows.filter((r) => scopeSet.has(r.id)) : rows),
    [rows, scopeIds], // eslint-disable-line react-hooks/exhaustive-deps
  );

  const fleet = useMemo(() => buildFleet(scopeRows), [scopeRows]);
  const board = useMemo(
    () => buildDimensionsBoard(scopeRows, now, summariesById),
    [scopeRows, now, summariesById],
  );
  const attention = useMemo(() => buildAttention(scopeRows), [scopeRows]);
  const orderedRows = useMemo(() => sortRows(scopeRows, sortDir), [scopeRows, sortDir]);
  const dimensionView = useMemo(
    () => (view === 'fleet' ? null : buildDimensionView(view, scopeRows, now, summariesById)),
    [view, scopeRows, now, summariesById],
  );

  const updateScope = useCallback((ids) => {
    setScopeIds(ids);
    storeScope(ids);
  }, []);

  const toggleProject = useCallback((id) => {
    const current = scopeIds == null ? rows.map((r) => r.id) : scopeIds;
    const next = current.includes(id)
      ? current.filter((x) => x !== id)
      : current.concat([id]);
    updateScope(next.length === rows.length ? null : next);
  }, [scopeIds, rows, updateScope]);

  const selectFlagged = useCallback(() => {
    const flagged = rows
      .filter((r) => consequenceLevel(consequenceOf(r)) !== 'clear')
      .map((r) => r.id);
    updateScope(flagged.length ? flagged : null);
  }, [rows, updateScope]);

  const openDimension = useCallback((key) => {
    setPickerOpen(false);
    if (dimension) onSwitchDimension?.(key);
    else onOpenDimension?.(key);
  }, [dimension, onOpenDimension, onSwitchDimension]);

  // The route component stays mounted across the fleet <-> dimension swap,
  // so reset the scroll container ourselves on every view change.
  const rootRef = useRef(null);
  useEffect(() => {
    rootRef.current?.closest('main')?.scrollTo?.(0, 0);
  }, [view]);

  if (!projectsLoaded) {
    return <div className="compare-page" ref={rootRef}><div className="compare-loading">{t('compare.loading')}</div></div>;
  }

  if (!localProjects.length) {
    return (
      <div className="compare-page" ref={rootRef}>
        <EmptyState
          title={t('compare.emptyTitle')}
          description={t('compare.emptyBody')}
        />
      </div>
    );
  }

  const scopeCount = scopeSet && scopeSet.size ? scopeRows.length : rows.length;
  const shared = {
    rows,
    orderedRows,
    scopeRows,
    fleet,
    board,
    attention,
    errorsById,
    sortDir,
    toggleSortDir: () => setSortDir((d) => (d === 'desc' ? 'asc' : 'desc')),
    hasCoverage: scopeRows.some((r) => r.coveragePct != null),
    pickerOpen,
    setPickerOpen,
    scopeIds,
    scopeCount,
    toggleProject,
    selectAll: () => updateScope(null),
    selectFlagged,
    openDimension,
    onOpenProject,
    now,
  };

  return (
    <div className="compare-page dashboard-fade" ref={rootRef}>
      {dimensionView ? (
        <CompareDimensionView
          view={dimensionView}
          board={board}
          fleet={fleet}
          onBack={onBack}
          onOpenDimension={openDimension}
          onOpenProject={onOpenProject}
        />
      ) : (
        <CompareFleetView {...shared} />
      )}
    </div>
  );
}
