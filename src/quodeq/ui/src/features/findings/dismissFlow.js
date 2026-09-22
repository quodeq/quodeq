/**
 * The dismiss-finding use case, shared by every route that can dismiss.
 *
 * The payload construction, target-project resolution and the four-step
 * follow-up tail (dismiss POST → applyDelta → scheduleDashboardReconcile →
 * bumpDismissRefresh) used to be copy-pasted across three route renderers.
 * The targetProject resolution in particular is the recurring
 * identity-divergence class from the assistant dismiss bug: one resolver,
 * one place, so the three call sites cannot drift apart again.
 */

/** Normalize a violation object into the dismiss POST payload. */
export function buildDismissPayload(v, fallbackDimension) {
  const fileParts = (v.file || '').split(':');
  const file = fileParts[0];
  const line = v.line ?? (fileParts[1] ? parseInt(fileParts[1], 10) : 0);
  return {
    req: v.req || v.principle,
    file,
    line,
    dimension: v.dimension || fallbackDimension || '',
    severity: v.severity,
    title: v.title || '',
    reason: v.reason,
    reqRefs: v.reqRefs || [],
    context: v.context || '',
    snippet: v.snippet || '',
    scope: v.scope || '',
    endLine: v.endLine || 0,
    principle: v.principle || '',
  };
}

/**
 * Which project the dismiss must land in. The entry's OWN project, not the
 * global selection: a cross-project entry (Compare's principle jump, a file
 * opened from a cross-project explorer, a parent dimension's fromProject)
 * must dismiss into the project the finding belongs to.
 */
export function resolveDismissTargetProject({ explicitProject, selectedProject }) {
  return explicitProject || selectedProject;
}

/**
 * Dismiss a finding and run the shared reconcile tail.
 *
 * POST returns { scores: { dimensions, summary } } — the rescored payload for
 * this run — plus a delta the caller-supplied applyDelta patches into the
 * dashboard/scores caches so the visible screen updates instantly. One
 * reconcile call per suppression mutation: scheduleDashboardReconcile marks
 * the project queries stale synchronously AND schedules the debounced active
 * refetch (see useDashboard.js), so a separate refreshDashboard call here
 * would be redundant.
 *
 * @param {{
 *   violation: Object,
 *   fallbackDimension?: string,
 *   runId?: string,
 *   explicitProject?: string,
 *   selectedProject?: string,
 *   deps: {
 *     dismissFinding: (project: string, payload: Object) => Promise<Object>,
 *     applyDelta?: (project: string, scores: Object, delta: Object) => void,
 *     scheduleDashboardReconcile?: () => void,
 *     bumpDismissRefresh?: () => void,
 *   },
 * }} args
 * @returns {Promise<Object>} the dismiss response (scores + delta)
 */
export async function dismissWithReconcile({
  violation, fallbackDimension, runId, explicitProject, selectedProject, deps,
}) {
  const payload = { ...buildDismissPayload(violation, fallbackDimension), run_id: runId };
  const targetProject = resolveDismissTargetProject({ explicitProject, selectedProject });
  const result = await deps.dismissFinding(targetProject, payload);
  deps.applyDelta?.(targetProject, result?.scores, result?.delta);
  deps.scheduleDashboardReconcile?.();
  deps.bumpDismissRefresh?.();
  return result;
}
