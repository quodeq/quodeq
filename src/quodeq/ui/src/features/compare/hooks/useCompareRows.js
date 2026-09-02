import { useMemo, useCallback } from 'react';
import {
  buildRow, buildFleet, buildDimensionsBoard, buildAttention,
  buildDimensionView, buildDuelView, sortRows,
} from '../compareModel.js';

/**
 * Every row + its "open this project" affordance: rows carry their own
 * source, so a remote row switches the app to the shared source instead of
 * asking the local registry for a project it lacks.
 */
function useFleetRows({ fleetProjects, summariesById, now, onOpenProject }) {
  const rows = useMemo(() => {
    const built = fleetProjects.map((p) => buildRow(p, summariesById[p.id || p.name], now));
    // Shared summaries pass through unfiltered (a remote project has no
    // local standards config), so a standard the user disabled everywhere
    // could re-enter the fleet through a remote row. The fleet speaks the
    // standards the LOCAL projects have enabled: remote rows trim to that
    // union. A remote-only fleet keeps everything - there is no local
    // configuration to defer to.
    const localKeys = new Set(
      built.filter((r) => !r.remote).flatMap((r) => r.dims.map((d) => d.key)),
    );
    if (!localKeys.size) return built;
    return built.map((r) => (r.remote
      ? { ...r, dims: r.dims.filter((d) => localKeys.has(d.key)) }
      : r));
  }, [fleetProjects, summariesById, now]);

  const openProject = useCallback((rowId) => {
    const row = rows.find((r) => r.id === rowId);
    onOpenProject?.(row?.sourceId ?? rowId, row?.source ?? 'local');
  }, [rows, onOpenProject]);

  return { rows, openProject };
}

/**
 * Builds every row/aggregate/derived-view ComparePage renders, from the
 * merged fleet projects down through the active scope, sort and drill-down.
 *
 * `duelView` deliberately reads `rows`, not `scopeRows`: the duel entry pins
 * two ids up front, and editing the scope afterwards must not blank an
 * already-open duel.
 */
export function useCompareRows({
  fleetProjects, summariesById, now, scopeIds, sortDir, view, duel, onOpenProject,
}) {
  const { rows, openProject } = useFleetRows({ fleetProjects, summariesById, now, onOpenProject });

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
  // Duel rows come from `rows`, not `scopeRows` — see the module doc above.
  const duelView = useMemo(
    () => (Array.isArray(duel) && duel.length === 2
      ? buildDuelView(duel[0], duel[1], rows, now, summariesById)
      : null),
    [duel, rows, now, summariesById],
  );

  return {
    rows, openProject, scopeSet, scopeRows, fleet, board, attention,
    orderedRows, dimensionView, duelView,
  };
}
