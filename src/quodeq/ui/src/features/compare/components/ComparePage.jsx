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
 * the whole screen. Row/aggregate building lives in useCompareRows, scope
 * selection in useCompareScopeActions, and the principle drill-down fetch in
 * useOpenPrinciple — this component only owns navigation state and layout.
 */
import { useMemo, useState, useCallback, useEffect, useRef } from 'react';
import EmptyState from '../../../components/EmptyState.jsx';
import CompareSkeleton from './CompareSkeleton.jsx';
import { t } from '../../../strings/index.js';
import { useCompareData, useSharedCompareProjects } from '../hooks/useCompareData.js';
import { useCompareRows } from '../hooks/useCompareRows.js';
import { useCompareScopeActions } from '../hooks/useCompareScopeActions.js';
import { useOpenPrinciple } from '../hooks/useOpenPrinciple.js';
import { mergeProjects } from '../../dashboard/projectsMerge.js';
import { readStoredScope } from '../compareScopeStorage.js';
import CompareFleetView from './CompareFleetView.jsx';
import CompareDimensionView from './CompareDimensionView.jsx';
import CompareDuelView from './CompareDuelView.jsx';

function buildSharedProps({
  rows, orderedRows, scopeRows, fleet, board, attention, errorsById, sortDir, setSortDir,
  hasCoverage, pickerOpen, setPickerOpen, scopeIds, scopeCount, toggleProject, selectAll,
  selectFlagged, openDimension, onOpenProjectDimension, onOpenDuel, openProject, now,
}) {
  return {
    rows, orderedRows, scopeRows, fleet, board, attention, errorsById, sortDir,
    toggleSortDir: () => setSortDir((d) => (d === 'desc' ? 'asc' : 'desc')),
    hasCoverage, pickerOpen, setPickerOpen, scopeIds, scopeCount, toggleProject,
    selectAll, selectFlagged, openDimension,
    // Expanded-row dimension chips jump to that project's own dimension
    // screen; the compare drill-down stays on the DIMENSIONS panel.
    onOpenProjectDimension,
    // "compare these two" only makes sense for a scope of exactly two; the
    // fleet header shows the action whenever that holds (whether the pair
    // was picked explicitly or the fleet just has two projects).
    openDuel: scopeRows.length === 2 && onOpenDuel
      ? () => { setPickerOpen(false); onOpenDuel([scopeRows[0].id, scopeRows[1].id]); }
      : null,
    // A duel can also start from any row's expansion ("compare with…") —
    // no need to narrow the scope to two first.
    openDuelPair: onOpenDuel ? (idA, idB) => onOpenDuel([idA, idB]) : null,
    onOpenProject: openProject,
    now,
  };
}

/**
 * Local projects plus the merged fleet (local rows + unclaimed shared-repo
 * rows). Remote projects from the configured shared repository join as
 * ordinary rows (empty list when nothing is configured). Duplicates resolve
 * with the Projects page's own precedence rule (projectsMerge.js): a shared
 * entry claimed by a local project — same id, else same normalized git
 * origin URL, never name alone — IS that project, and the local row
 * prevails. Only unclaimed shared entries enter as remote rows.
 */
function useFleetProjects(projects) {
  const localProjects = useMemo(
    () => (projects || []).filter((p) => p && (p.id || p.name)),
    [projects],
  );
  const sharedProjects = useSharedCompareProjects();
  const fleetProjects = useMemo(() => {
    const entries = mergeProjects(localProjects, sharedProjects);
    return entries.map((e) => {
      if (e.local) return e.local;
      const raw = e.shared.id || e.shared.name;
      return { ...e.shared, id: `shared:${raw}`, sourceId: raw, source: 'shared' };
    });
  }, [localProjects, sharedProjects]);
  return { localProjects, fleetProjects };
}

/**
 * Everything view/scope-state-shaped: score ordering, the scope picker,
 * the built rows/aggregates (useCompareRows), scope actions
 * (useCompareScopeActions), the principle drill-down fetch
 * (useOpenPrinciple), and the dimension-open callback (which follows the
 * push-vs-replace nav contract described on the component below).
 */
function useComparePageState({
  fleetProjects, summariesById, dimension, duel, onOpenProject, onOpenDimension,
  onSwitchDimension, onOpenEvalPrincipal,
}) {
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

  const rowsState = useCompareRows({ fleetProjects, summariesById, now, scopeIds, sortDir, view, duel, onOpenProject });
  const { toggleProject, selectAll, selectFlagged } = useCompareScopeActions({ scopeIds, setScopeIds, rows: rowsState.rows });
  const openPrinciple = useOpenPrinciple({ onOpenEvalPrincipal, openProject: rowsState.openProject });

  const openDimension = useCallback((key) => {
    setPickerOpen(false);
    if (dimension) onSwitchDimension?.(key);
    else onOpenDimension?.(key);
  }, [dimension, onOpenDimension, onSwitchDimension]);

  return {
    view, sortDir, setSortDir, pickerOpen, setPickerOpen, scopeIds, now,
    ...rowsState, toggleProject, selectAll, selectFlagged, openPrinciple, openDimension,
  };
}

/**
 * `dimension` and `duel` follow the same nav-stack-entry contract as every
 * route param here: dimension arrives as a route param (drilling in
 * pushes, browser back returns to the fleet, switching dimensions
 * replaces, the back control pops); duel holds the two project ids,
 * pushed from the fleet's "compare these two" action (back pops to the
 * fleet).
 */
function comparePageStatus(projectsLoaded, localProjects, rootRef) {
  if (!projectsLoaded) {
    return <div className="compare-page" ref={rootRef}><CompareSkeleton /></div>;
  }
  if (!localProjects.length) {
    return (
      <div className="compare-page" ref={rootRef}>
        <EmptyState title={t('compare.emptyTitle')} description={t('compare.emptyBody')} />
      </div>
    );
  }
  return null;
}

/** Picks the active view: duel, dimension drill-down, or the fleet landing
 * page. */
function ComparePageBody({ duelView, dimensionView, board, fleet, openDimension, openProject, openPrinciple, onOpenProjectDimension, shared }) {
  if (duelView) return <CompareDuelView duel={duelView} onOpenProject={openProject} />;
  if (dimensionView) {
    return (
      <CompareDimensionView
        view={dimensionView}
        board={board}
        fleet={fleet}
        onOpenDimension={openDimension}
        onOpenProject={openProject}
        onOpenPrinciple={openPrinciple}
        onOpenProjectDimension={onOpenProjectDimension}
      />
    );
  }
  return <CompareFleetView {...shared} />;
}

export default function ComparePage({
  projects, projectsLoaded, onOpenProject,
  dimension = null,
  onOpenDimension,
  onSwitchDimension,
  onOpenEvalPrincipal,
  onOpenProjectDimension,
  duel = null,
  onOpenDuel,
}) {
  const { localProjects, fleetProjects } = useFleetProjects(projects);
  const { summariesById, errorsById } = useCompareData(fleetProjects);
  const {
    view, sortDir, setSortDir, pickerOpen, setPickerOpen, scopeIds, now,
    rows, openProject, scopeSet, scopeRows, fleet, board, attention,
    orderedRows, dimensionView, duelView,
    toggleProject, selectAll, selectFlagged, openPrinciple, openDimension,
  } = useComparePageState({
    fleetProjects, summariesById, dimension, duel, onOpenProject, onOpenDimension,
    onSwitchDimension, onOpenEvalPrincipal,
  });

  // The route component stays mounted across the fleet <-> dimension swap,
  // so reset the scroll container ourselves on every view change.
  const rootRef = useRef(null);
  useEffect(() => {
    rootRef.current?.closest('main')?.scrollTo?.(0, 0);
  }, [view, duel]);

  const status = comparePageStatus(projectsLoaded, localProjects, rootRef);
  if (status) return status;

  const scopeCount = scopeSet && scopeSet.size ? scopeRows.length : rows.length;
  const shared = buildSharedProps({
    rows, orderedRows, scopeRows, fleet, board, attention, errorsById, sortDir, setSortDir,
    hasCoverage: scopeRows.some((r) => r.coveragePct != null),
    pickerOpen, setPickerOpen, scopeIds, scopeCount, toggleProject, selectAll, selectFlagged,
    openDimension, onOpenProjectDimension, onOpenDuel, openProject, now,
  });

  return (
    <div className="compare-page dashboard-fade" ref={rootRef}>
      <ComparePageBody
        duelView={duelView} dimensionView={dimensionView} board={board} fleet={fleet}
        openDimension={openDimension} openProject={openProject} openPrinciple={openPrinciple}
        onOpenProjectDimension={onOpenProjectDimension} shared={shared}
      />
    </div>
  );
}
