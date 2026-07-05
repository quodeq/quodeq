/**
 * Patch the React Query dashboard/scores caches from a dismiss mutation delta.
 *
 * The dismiss endpoint returns a ``delta`` describing the mutation; this writer
 * folds it into the cached dashboard/scores payloads so the Overview updates
 * instantly, without waiting for a refetch. It is ADDITIVE — the existing
 * refreshDashboard / bumpDismissRefresh mechanisms still run; they just no
 * longer gate the perceived latency of a dismiss.
 *
 * Referential identity is a hard requirement: untouched dimensions must keep
 * their object identity so downstream memoized selectors don't re-render the
 * whole page. Only the patched/spliced dimension gets a new reference — we
 * never map through model factories or deep-clone inside the updater.
 */
import { projectKeys } from "./queryKeys";

// Same key convention as mergeRescoreIntoEval (explorerDataHooks.js): a
// violation is identified by req|file|line, defaulting missing parts.
function violationKey(v) {
  return `${v?.req || ""}|${v?.file || ""}|${v?.line || 0}`;
}

function clampNonNegative(n) {
  return Math.max(0, n | 0);
}

/**
 * Remove the dismissed violation from a dimension and decrement its totals.
 * Returns the SAME dimension object unchanged when the violation isn't present,
 * preserving referential identity.
 */
function removeDismissed(dim, dismissed) {
  const violations = dim?.violations;
  if (!Array.isArray(violations)) return dim;
  const targetKey = violationKey(dismissed);
  const idx = violations.findIndex((v) => violationKey(v) === targetKey);
  if (idx === -1) return dim;

  const removed = violations[idx];
  const nextViolations = violations.filter((_, i) => i !== idx);

  const prevTotals = dim.totals || {};
  const prevSeverity = prevTotals.severity || {};
  const removedSeverity = (removed?.severity || "").toLowerCase();
  const nextSeverity = { ...prevSeverity };
  if (removedSeverity && nextSeverity[removedSeverity] != null) {
    nextSeverity[removedSeverity] = clampNonNegative(nextSeverity[removedSeverity] - 1);
  }
  const nextTotals = {
    ...prevTotals,
    violationCount: clampNonNegative((prevTotals.violationCount || 0) - 1),
    severity: nextSeverity,
  };

  return { ...dim, violations: nextViolations, totals: nextTotals };
}

/**
 * Apply the rescored per-dimension score/grade to a dimension when present in
 * scoreByDim. Returns the SAME object when there's nothing to patch.
 */
function patchDimScore(dim, scoreByDim) {
  const resc = scoreByDim.get(dim?.dimension);
  if (!resc) return dim;
  return {
    ...dim,
    overallScore: resc.overallScore ?? dim.overallScore,
    overallGrade: resc.overallGrade ?? dim.overallGrade,
  };
}

export function applyMutationDelta(queryClient, projectId, delta) {
  if (!queryClient || !projectId || !delta) return;
  if (delta.kind !== "dismiss") return;

  const dims = Array.isArray(delta.dimensions) ? delta.dimensions : [];
  const scoreByDim = new Map(dims.map((d) => [d.dimension, d]));
  const dismissed = delta.dismissed || {};

  // Dashboard cache: patch score + splice the dismissed violation from totals.
  const patchDashboard = (key) => {
    const prev = queryClient.getQueryData(key);
    if (!prev || !Array.isArray(prev.dimensions)) {
      queryClient.invalidateQueries({ queryKey: key, refetchType: "none" });
      return;
    }
    queryClient.setQueryData(key, (old) => ({
      ...old,
      dimensions: old.dimensions.map((dim) =>
        removeDismissed(patchDimScore(dim, scoreByDim), dismissed),
      ),
    }));
  };

  // Per-run scores cache: slim violations, so just refresh the dim score/grade.
  const patchRunScores = (key) => {
    const prev = queryClient.getQueryData(key);
    if (!prev || !Array.isArray(prev.dimensions)) {
      queryClient.invalidateQueries({ queryKey: key, refetchType: "none" });
      return;
    }
    queryClient.setQueryData(key, (old) => ({
      ...old,
      dimensions: old.dimensions.map((dim) => patchDimScore(dim, scoreByDim)),
    }));
  };

  // Accumulated (cross-run) scores cache: the server sent the whole rollup, so
  // swap it in wholesale; if absent, invalidate (it's small — a default refetch
  // is fine).
  const patchAccumulated = (key, accumulated) => {
    const prev = queryClient.getQueryData(key);
    if (!accumulated || !prev) {
      queryClient.invalidateQueries({ queryKey: key });
      return;
    }
    queryClient.setQueryData(key, (old) => ({ ...old, accumulated }));
  };

  const runId = delta.runId;
  if (runId) {
    patchDashboard(projectKeys.dashboard(projectId, runId));
    patchRunScores(projectKeys.scores(projectId, runId));
  }

  if (delta.isLatest) {
    patchDashboard(projectKeys.dashboard(projectId, "latest"));
    patchAccumulated(projectKeys.scores(projectId, null), delta.accumulated);
  }
}
