/**
 * Patch the React Query dashboard, run findings and scores caches from a
 * mutation delta.
 *
 * The dismiss endpoint returns a ``delta`` describing the mutation; this writer
 * folds it into the cached dashboard/scores payloads so the Overview updates
 * instantly, without waiting for a refetch. It is ADDITIVE — the existing
 * refreshDashboard / recordDismissed mechanisms still run; they just no
 * longer gate the perceived latency of a dismiss.
 *
 * Referential identity is a hard requirement: untouched dimensions must keep
 * their object identity so downstream memoized selectors don't re-render the
 * whole page. Only the patched/spliced dimension gets a new reference — we
 * never map through model factories or deep-clone inside the updater.
 */
import { projectKeys } from "./queryKeys";
import { violationKey } from "../utils/violationKey.js";
import { LATEST_RUN_ID } from "../constants.js";
import { DEFAULT_PROJECT_SOURCE } from "../vocab/projectSource.js";

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
 * Apply the rescored per-dimension score/grade, and the recounted totals
 * when the server sent them, to a dimension present in scoreByDim. Returns
 * the SAME object when there's nothing to patch.
 */
function patchDimScore(dim, scoreByDim) {
  const resc = scoreByDim.get(dim?.dimension);
  if (!resc) return dim;
  return {
    ...dim,
    overallScore: resc.overallScore ?? dim.overallScore,
    overallGrade: resc.overallGrade ?? dim.overallGrade,
    totals: resc.totals ?? dim.totals,
  };
}

// Kinds this writer understands. dismiss splices the violation locally; the
// rest (restore/delete and their -all bulk forms, and dismiss_many for a
// whole requirement type, whose removed keys are not in the delta) can't
// cheaply/correctly reconstruct the violation-list change, so they
// invalidate the run-detail violation source and let it refetch on next view.
const MUTATION_KIND_DISMISS = "dismiss"; // the one kind that splices the cached violation list locally
const KNOWN_KINDS = new Set([MUTATION_KIND_DISMISS, "restore", "delete", "restore_all", "delete_all", "dismiss_many"]);

// Patch dim score/grade (and totals) in place, preserving referential
// identity for untouched dims. ``spliceDismissed`` additionally removes the
// dismissed violation from the run findings cache (the one cache with
// violation arrays); the dashboard overview and the accumulated scores carry
// counts only, so the server's recounted totals cover them. The splice runs
// first so a dim the delta did not rescore still loses the row and one count.
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
        const spliced = spliceDismissed ? removeDismissed(dim, dismissed) : dim;
        return patchDimScore(spliced, scoreByDim);
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
        dimensions: old.accumulated.dimensions.map((dim) =>
          dim?.fromRunId === runId ? patchDimScore(dim, scoreByDim) : dim,
        ),
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

// The dashboard entry (overview shape: scores and counts, no lists).
const overviewKey = (projectId, runId) => projectKeys.dashboard(projectId, runId, DEFAULT_PROJECT_SOURCE);

function applyRunScopedPatches({ runId, projectId, patchScores, invalidateViolations, splices }) {
  if (!runId) return;
  const dashKey = overviewKey(projectId, runId);
  const findingsKey = projectKeys.runScores(projectId, runId);
  const scoresKey = projectKeys.scores(projectId, runId);
  // Score-patch is shared across all kinds; the run findings (the run page's
  // and the Explorer's lists) additionally splice for dismiss.
  patchScores(dashKey);
  patchScores(findingsKey, { spliceDismissed: splices });
  patchScores(scoresKey);
  // Non-dismiss kinds can't mirror the violation-list change locally →
  // invalidate the run-detail sources so they refetch (scores already patched).
  if (!splices) {
    invalidateViolations(findingsKey);
    invalidateViolations(scoresKey);
  }
}

function applyLatestPatches({ delta, projectId, runId, patchScores, patchAccumulated, patchAccumulatedDims }) {
  if (!delta.isLatest) return;
  patchScores(overviewKey(projectId, LATEST_RUN_ID));
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

/**
 * Folds a mutation response's `delta` into the React Query caches so scores,
 * grades and violation lists reflect a dismiss/restore/delete immediately
 * instead of waiting for a refetch.
 *
 * A dismiss splices the finding out of the cached run findings (it carries
 * the full violation key); every other kind invalidates the affected lists
 * instead. Counts come from the rescored dimensions' totals. Unknown kinds
 * and missing arguments are no-ops.
 *
 * @param {import('@tanstack/react-query').QueryClient} queryClient
 * @param {string} projectId
 * @param {{kind: string, runId?: string, dimensions?: Array<object>, dismissed?: object}} delta
 */
export function applyMutationDelta(queryClient, projectId, delta) {
  if (!queryClient || !projectId || !delta) return;
  if (!KNOWN_KINDS.has(delta.kind)) return;

  const dims = Array.isArray(delta.dimensions) ? delta.dimensions : [];
  const scoreByDim = new Map(dims.map((d) => [d.dimension, d]));
  const dismissed = delta.dismissed || {};
  // Only dismiss can splice locally — it carries the full violation key and is
  // a single-finding removal. Every other kind invalidates instead.
  const splices = delta.kind === MUTATION_KIND_DISMISS;
  const runId = delta.runId;

  const patchScores = makePatchScores(queryClient, scoreByDim, dismissed);
  const patchAccumulated = makePatchAccumulated(queryClient);
  const patchAccumulatedDims = makePatchAccumulatedDims(queryClient, scoreByDim, runId);
  const invalidateViolations = makeInvalidateViolations(queryClient);

  applyRunScopedPatches({ runId, projectId, patchScores, invalidateViolations, splices });
  applyLatestPatches({ delta, projectId, runId, patchScores, patchAccumulated, patchAccumulatedDims });
}
