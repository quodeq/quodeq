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

// Kinds this writer understands. dismiss splices the violation locally; the
// rest (restore/delete and their -all bulk forms) can't cheaply/correctly
// reconstruct the violation-list change, so they invalidate the run-detail
// violation source and let it refetch on next view.
const KNOWN_KINDS = new Set(["dismiss", "restore", "delete", "restore_all", "delete_all"]);

export function applyMutationDelta(queryClient, projectId, delta) {
  if (!queryClient || !projectId || !delta) return;
  if (!KNOWN_KINDS.has(delta.kind)) return;

  const dims = Array.isArray(delta.dimensions) ? delta.dimensions : [];
  const scoreByDim = new Map(dims.map((d) => [d.dimension, d]));
  const dismissed = delta.dismissed || {};
  // Only dismiss can splice locally — it carries the full violation key and is
  // a single-finding removal. Every other kind invalidates instead.
  const splices = delta.kind === "dismiss";

  // Patch dim score/grade in place, preserving referential identity for
  // untouched dims. ``spliceDismissed`` additionally removes the dismissed
  // violation from the dashboard cache (which carries full violation arrays);
  // the per-run scores cache is slim so it never splices.
  const patchScores = (key, { spliceDismissed = false } = {}) => {
    const prev = queryClient.getQueryData(key);
    if (!prev || !Array.isArray(prev.dimensions)) {
      queryClient.invalidateQueries({ queryKey: key, refetchType: "none" });
      return;
    }
    queryClient.setQueryData(key, (old) => ({
      ...old,
      dimensions: old.dimensions.map((dim) => {
        const scored = patchDimScore(dim, scoreByDim);
        return spliceDismissed ? removeDismissed(scored, dismissed) : scored;
      }),
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

  // Invalidate the run-detail violation source so lists refetch on next view.
  // refetchType:"none" keeps it lazy — no eager network churn while scores
  // already updated instantly via the score-patch above.
  const invalidateViolations = (key) => {
    queryClient.invalidateQueries({ queryKey: key, refetchType: "none" });
  };

  const runId = delta.runId;
  if (runId) {
    const dashKey = projectKeys.dashboard(projectId, runId);
    const scoresKey = projectKeys.scores(projectId, runId);
    // Score-patch is shared across all kinds; dashboard additionally splices
    // for dismiss.
    patchScores(dashKey, { spliceDismissed: splices });
    patchScores(scoresKey);
    // Non-dismiss kinds can't mirror the violation-list change locally →
    // invalidate the run-detail sources so they refetch (scores already patched).
    if (!splices) {
      invalidateViolations(dashKey);
      invalidateViolations(scoresKey);
    }
  }

  if (delta.isLatest) {
    patchScores(projectKeys.dashboard(projectId, "latest"), { spliceDismissed: splices });
    patchAccumulated(projectKeys.scores(projectId, null), delta.accumulated);
  }
}
