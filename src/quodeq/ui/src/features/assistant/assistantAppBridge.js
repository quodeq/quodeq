/**
 * App-level assistant glue, moved out of App.jsx (move-only): the session
 * payload builder and the applied-action window-event handler. Both are pure
 * builders exported so their contracts stay testable without mounting App.
 */

// Exported for tests: the session-start payload must carry the selected
// source so remote projects get read-only sessions server-side.
export function buildAssistantSessionPayload({ provider, model, projectId, runId, source }) {
  return { provider, model, projectId, runId, source };
}

/**
 * Handler for the `quodeq:assistant-action-applied` window event, which the
 * assistant's ActionPreviewCard dispatches after a successful apply.
 *
 * Extracted and exported so the post-dismiss convergence contract can be
 * pinned without mounting App (which needs ~8 providers). An assistant
 * dismiss mutates exactly the payloads a manual dismiss does, so it owes the
 * same three follow-ups — see the inline notes on each.
 *
 * @param {{
 *   applyDelta: (project: string, scores: Object, delta: Object) => void,
 *   bumpDismissRefresh: () => void,
 *   scheduleDashboardReconcile?: () => void,
 *   selectedProject: string,
 * }} deps
 * @returns {(event: CustomEvent) => void}
 */
export function buildAssistantActionAppliedHandler({
  applyDelta,
  bumpDismissRefresh,
  scheduleDashboardReconcile,
  selectedProject,
}) {
  return (event) => {
    if (event.detail?.actionType !== 'dismiss_finding') return;
    // Apply the delta first so the currently-visible screen patches in place
    // immediately; the refresh/reconcile below are the eventual-correctness
    // path (e.g. for views the delta doesn't cover).
    // Prefer the delta's own project over the live selectedProject: the
    // apply POST may resolve after the user switched projects, and the
    // delta is frozen to the action's project. Keying the patch on the
    // live selection would write project A's rollup into project B's cache.
    if (event.detail.delta) {
      try {
        applyDelta(
          event.detail.delta?.project || selectedProject,
          event.detail.scores,
          event.detail.delta,
        );
      } catch {
        // Instant patch is best-effort; the refresh/reconcile are the fallback.
      }
    }
    bumpDismissRefresh();
    // Reconcile exactly as the manual dismiss handlers do: the call below
    // marks the project queries stale synchronously (so frozen run views
    // refetch on their next mount) and then actively refetches after the
    // debounce window
    // (see useDismissedFindings.js). Mark-stale alone never reaches the
    // Overview: its useDashboard observer is mounted at the app root and
    // never remounts, and the pywebview window never fires the focus-refetch
    // a browser tab gets. So for any view the delta above doesn't cover --
    // and for an assistant dismiss that returns no delta at all -- the
    // visible screen would keep showing pre-dismiss numbers indefinitely,
    // which reads as "nothing updated". Debounced, so a multi-action apply
    // coalesces into one refetch of the 10-20 MB payload.
    //
    // Unlike applyDelta this keys on the LIVE selectedProject rather than the
    // delta's frozen project. That is safe here
    // where it wouldn't be above: reconciling is a refetch, so aiming it at
    // the wrong project after a mid-flight switch merely re-pulls fresh data;
    // it never writes one project's rollup into another's cache.
    scheduleDashboardReconcile?.();
  };
}
