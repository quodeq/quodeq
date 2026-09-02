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

// Patch dim score/grade in place, preserving referential identity for
// untouched dims. ``spliceDismissed`` additionally removes the dismissed
// violation from the dashboard cache (which carries full violation arrays);
// the per-run scores cache is slim so it never splices.
function makePatchScores(queryClient, scoreByDim, dismissed) {
  return (key, { spliceDismissed = false } = {}) => {
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
}

// Accumulated (cross-run) scores cache: when the server sent a whole rollup,
// swap it in wholesale; if absent, invalidate (it's small — a default refetch
// is fine). The dismiss/restore/delete deltas no longer carry one (computing
// it server-side ran compute_accumulated over every run — ~100s cold on large
// projects — and blew past the client's 30s timeout, aborting the whole
// delta), so this path is only taken by callers that still provide one.
function makePatchAccumulated(queryClient) {
  return (key, accumulated) => {
    const prev = queryClient.getQueryData(key);
    if (!accumulated || !prev) {
      queryClient.invalidateQueries({ queryKey: key });
      return;
    }
    queryClient.setQueryData(key, (old) => ({ ...old, accumulated }));
  };
}

// Client-derive the Overview's accumulated dimension grades from the per-run
// rescore instead of a server-computed rollup. The accumulated entry for each
// dimension the latest run OWNS (``fromRunId === runId``) equals that run's
// rescored dimension, so we copy overallScore/overallGrade across — no
// cross-run recompute, so the dismiss POST stays ~0.1s and never times out.
// The weighted overall summary is deliberately left untouched (a lazy refetch
// reconciles it); recomputing it here would duplicate the grade formula.
// No-op — crucially NOT an invalidate, which would trigger the slow refetch —
// when the entry isn't cached; it fills in on its next fetch.
function makePatchAccumulatedDims(queryClient, scoreByDim, runId) {
  return (key) => {
    const prev = queryClient.getQueryData(key);
    if (!Array.isArray(prev?.accumulated?.dimensions)) return;
    queryClient.setQueryData(key, (old) => ({
      ...old,
      accumulated: {
        ...old.accumulated,
        dimensions: old.accumulated.dimensions.map((dim) => {
          if (dim?.fromRunId !== runId) return dim;
          const resc = scoreByDim.get(dim?.dimension);
          if (!resc) return dim;
          return {
            ...dim,
            overallScore: resc.overallScore ?? dim.overallScore,
            overallGrade: resc.overallGrade ?? dim.overallGrade,
          };
        }),
      },
    }));
  };
}

// Invalidate the run-detail violation source so lists refetch on next view.
// refetchType:"none" keeps it lazy — no eager network churn while scores
// already updated instantly via the score-patch above.
function makeInvalidateViolations(queryClient) {
  return (key) => {
    queryClient.invalidateQueries({ queryKey: key, refetchType: "none" });
  };
}

function applyRunScopedPatches({ runId, projectId, patchScores, invalidateViolations, splices }) {
  if (!runId) return;
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

function applyLatestPatches({ delta, projectId, runId, patchScores, patchAccumulated, patchAccumulatedDims, splices }) {
  if (!delta.isLatest) return;
  patchScores(projectKeys.dashboard(projectId, "latest"), { spliceDismissed: splices });
  if (delta.accumulated) {
    // A caller supplied the authoritative rollup — prefer it.
    patchAccumulated(projectKeys.scores(projectId, null), delta.accumulated);
    if (runId) patchAccumulated(projectKeys.scores(projectId, runId), delta.accumulated);
  } else if (runId) {
    // Client-derive from the per-run rescore. The Overview's app-root
    // useDashboard reads `accumulated` from the null "latest" entry OR the
    // run-scoped scores(projectId, runId) entry (the latter the moment the
    // user drills into any run / dimension detail — see useProjectScores asOf
    // resolution). Both are patched: the run-scoped entry has
    // staleTime:Infinity and refreshDashboard only marks it stale
    // (refetchType:"none"), so without this the Overview grade cards would sit
    // stale until a window-focus refetch.
    patchAccumulatedDims(projectKeys.scores(projectId, null));
    patchAccumulatedDims(projectKeys.scores(projectId, runId));
  }
}

export function applyMutationDelta(queryClient, projectId, delta) {
  if (!queryClient || !projectId || !delta) return;
  if (!KNOWN_KINDS.has(delta.kind)) return;

  const dims = Array.isArray(delta.dimensions) ? delta.dimensions : [];
  const scoreByDim = new Map(dims.map((d) => [d.dimension, d]));
  const dismissed = delta.dismissed || {};
  // Only dismiss can splice locally — it carries the full violation key and is
  // a single-finding removal. Every other kind invalidates instead.
  const splices = delta.kind === "dismiss";
  const runId = delta.runId;

  const patchScores = makePatchScores(queryClient, scoreByDim, dismissed);
  const patchAccumulated = makePatchAccumulated(queryClient);
  const patchAccumulatedDims = makePatchAccumulatedDims(queryClient, scoreByDim, runId);
  const invalidateViolations = makeInvalidateViolations(queryClient);

  applyRunScopedPatches({ runId, projectId, patchScores, invalidateViolations, splices });
  applyLatestPatches({ delta, projectId, runId, patchScores, patchAccumulated, patchAccumulatedDims, splices });
}
