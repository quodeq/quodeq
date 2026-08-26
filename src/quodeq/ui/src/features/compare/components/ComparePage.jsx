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
import { useQueryClient } from '@tanstack/react-query';
import EmptyState from '../../../components/EmptyState.jsx';
import CompareSkeleton from './CompareSkeleton.jsx';
import { getDimensionEval } from '../../../api/index.js';
import { projectKeys } from '../../../api/queryKeys.js';
import {
  buildEvalPrincipalFn,
  computeComplianceByPrinciple,
} from '../../explorer/components/explorerDataHooks.js';
import { t } from '../../../strings/index.js';
import { useCompareData, useSharedCompareProjects } from '../hooks/useCompareData.js';
import { mergeProjects } from '../../dashboard/projectsMerge.js';
import {
  buildRow, buildFleet, buildDimensionsBoard, buildAttention,
  buildDimensionView, buildDuelView, sortRows, consequenceOf, consequenceLevel,
} from '../compareModel.js';
import CompareFleetView from './CompareFleetView.jsx';
import CompareDimensionView from './CompareDimensionView.jsx';
import CompareDuelView from './CompareDuelView.jsx';

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
  onOpenEvalPrincipal,
  onOpenProjectDimension,
  /* The head-to-head view follows the same contract: `duel` is a route
     param holding the two project ids, pushed from the fleet's "compare
     these two" action; back pops to the fleet. */
  duel = null,
  onOpenDuel,
  onBack,
}) {
  const localProjects = useMemo(
    () => (projects || []).filter((p) => p && (p.id || p.name)),
    [projects],
  );
  // Remote projects from the configured shared repository join the fleet as
  // ordinary rows (empty list when nothing is configured). Duplicates
  // resolve with the Projects page's own precedence rule (projectsMerge.js):
  // a shared entry claimed by a local project — same id, else same
  // normalized git origin URL, never name alone — IS that project, and the
  // local row prevails. Only unclaimed shared entries enter as remote rows.
  const sharedProjects = useSharedCompareProjects();
  const fleetProjects = useMemo(() => {
    const entries = mergeProjects(localProjects, sharedProjects);
    return entries.map((e) => {
      if (e.local) return e.local;
      const raw = e.shared.id || e.shared.name;
      return { ...e.shared, id: `shared:${raw}`, sourceId: raw, source: 'shared' };
    });
  }, [localProjects, sharedProjects]);
  const { summariesById, errorsById } = useCompareData(fleetProjects);

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
    () => fleetProjects.map((p) => buildRow(p, summariesById[p.id || p.name], now)),
    [fleetProjects, summariesById, now],
  );

  // Every "open this project" affordance funnels through here: rows carry
  // their own source, so a remote row switches the app to the shared
  // source instead of asking the local registry for a project it lacks.
  const openProject = useCallback((rowId) => {
    const row = rows.find((r) => r.id === rowId);
    onOpenProject?.(row?.sourceId ?? rowId, row?.source ?? 'local');
  }, [rows, onOpenProject]);

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
  // Duel rows come from `rows`, not `scopeRows`: the entry pins two ids, and
  // editing the scope afterwards must not blank an already-open duel.
  const duelView = useMemo(
    () => (Array.isArray(duel) && duel.length === 2
      ? buildDuelView(duel[0], duel[1], rows, now, summariesById)
      : null),
    [duel, rows, now, summariesById],
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

  // Open one project's own view of one principle: fetch that project's
  // dimension eval (cached in its query subtree), build the evalPrincipal
  // with the explorer's own builders, and PUSH — the selected project does
  // not change, so browser back pops straight back to this drill-down.
  const queryClient = useQueryClient();
  const openPrinciple = useCallback(async (target) => {
    // Remote rows can't deep-link into local project pages; opening the
    // shared project itself is the honest fallback (same degradation the
    // standings rows use).
    if (target?.remote) { openProject(target.id); return; }
    if (!onOpenEvalPrincipal || !target?.runId || !target?.dimName) return;
    try {
      const evalData = await queryClient.fetchQuery({
        queryKey: projectKeys.dimensionEval(target.id, target.runId, target.dimName),
        queryFn: () => getDimensionEval(target.id, target.runId, target.dimName),
        staleTime: 60_000,
      });
      const evalPrincipal = buildEvalPrincipalFn(
        evalData,
        computeComplianceByPrinciple(evalData),
        target.id,
        target.runId,
        target.dateLabel || '',
      )(target.principle);
      onOpenEvalPrincipal(evalPrincipal);
    } catch {
      // Fetch failed (run pruned, server hiccup): stay on Compare rather
      // than landing on an empty principle page.
    }
  }, [onOpenEvalPrincipal, queryClient, openProject]);

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
  }, [view, duel]);

  if (!projectsLoaded) {
    return <div className="compare-page" ref={rootRef}><CompareSkeleton /></div>;
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

  return (
    <div className="compare-page dashboard-fade" ref={rootRef}>
      {duelView ? (
        <CompareDuelView
          duel={duelView}
          onBack={onBack}
          onOpenProject={openProject}
        />
      ) : dimensionView ? (
        <CompareDimensionView
          view={dimensionView}
          board={board}
          fleet={fleet}
          onBack={onBack}
          onOpenDimension={openDimension}
          onOpenProject={openProject}
          onOpenPrinciple={openPrinciple}
          onOpenProjectDimension={onOpenProjectDimension}
        />
      ) : (
        <CompareFleetView {...shared} />
      )}
    </div>
  );
}
