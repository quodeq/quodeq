/**
 * Holds the running evaluation's live values outside React state.
 *
 * The job status, its findings and its progress change on every poll tick. A
 * component subscribes to the one field it renders, so a tick re-renders that
 * component and nothing else.
 */

export const EMPTY_FINDINGS = {};

export const LIVE_EVALUATION_INITIAL_STATE = {
  job: null,
  jobError: null,
  liveViolations: EMPTY_FINDINGS,
  startedProject: null,
  progress: null,
  isEvaluating: false,
};

const LIVE_FIELDS = Object.keys(LIVE_EVALUATION_INITIAL_STATE);

function sameState(current, next) {
  return LIVE_FIELDS.every((field) => Object.is(current[field], next[field]));
}

/**
 * A subscribable snapshot of the live evaluation, plus stable action handles.
 *
 * `actions` keeps one identity for the app's lifetime and forwards to whatever
 * handlers the provider registered last, so callers wired far from the
 * provider (the onboarding wizard, the topbar) never hold a stale function.
 *
 * @returns {{actions: object, getState: () => object, subscribe: (fn: Function) => Function,
 *   setHandlers: (next: object) => void, publish: (next: object) => void}}
 */
export function createLiveEvaluationStore() {
  let state = LIVE_EVALUATION_INITIAL_STATE;
  const listeners = new Set();
  const handlers = { start: null, dismiss: null, cancel: null };

  const actions = {
    startEvaluation: (payload) => handlers.start?.(payload),
    dismissEvaluation: (action) => handlers.dismiss?.(action),
    cancelEvaluation: (options) => handlers.cancel?.(options),
  };

  function subscribe(listener) {
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  }

  function publish(next) {
    if (sameState(state, next)) return;
    state = next;
    for (const listener of [...listeners]) listener();
  }

  return {
    actions,
    getState: () => state,
    subscribe,
    setHandlers: (next) => { Object.assign(handlers, next); },
    publish,
  };
}
