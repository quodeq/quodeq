/**
 * Live evaluation state, published to subscribers instead of to the app root.
 *
 * The provider owns the job status, findings and progress queries. It sits
 * below the root and renders `children` unchanged, so a poll tick re-renders
 * the provider alone; the components that read a field re-render through their
 * own subscription. The store identity is created by the root
 * (`useLiveEvaluationStore`) so the root can read `isEvaluating` — which flips
 * once per run, not once per tick — and hold the start/cancel handles.
 */
import { createContext, useContext, useLayoutEffect, useMemo, useRef, useSyncExternalStore } from 'react';
import { useEvaluationLifecycle } from '../../hooks/useEvaluationLifecycle.js';
import { useEvaluationProgress } from './hooks/useEvaluationProgress.js';
import { computeOverallProgress } from './components/scanProgressTotals.js';
import {
  createLiveEvaluationStore, LIVE_EVALUATION_INITIAL_STATE, EMPTY_FINDINGS,
} from './liveEvaluationStore.js';
import { JOB_STATUS } from '../../vocab/jobStatus.js';
import { DIM_STATE } from '../../vocab/dimState.js';

const EvaluationLiveContext = createContext(null);

const EMPTY_DIMENSION_FINDINGS = [];
const NO_ACTIONS = {
  startEvaluation: () => undefined,
  dismissEvaluation: () => undefined,
  cancelEvaluation: () => undefined,
};
const noopSubscribe = () => () => {};

/** One store per app instance, created before the provider mounts. */
export function useLiveEvaluationStore() {
  const storeRef = useRef(null);
  if (!storeRef.current) storeRef.current = createLiveEvaluationStore();
  return storeRef.current;
}

/**
 * Subscribe to one field of a store held outside the context, for callers
 * rendered above the provider. `select` must return a value the store keeps by
 * reference; returning a fresh object on every call would re-render forever.
 */
export function useLiveEvaluationValue(store, select) {
  const read = () => select(store ? store.getState() : LIVE_EVALUATION_INITIAL_STATE);
  return useSyncExternalStore(store ? store.subscribe : noopSubscribe, read, read);
}

function useLiveField(select) {
  return useLiveEvaluationValue(useContext(EvaluationLiveContext), select);
}

/** The running job, or null. */
export function useLiveJob() {
  return useLiveField((state) => state.job);
}

/** The last start/cancel/resume failure message, or null. */
export function useLiveJobError() {
  return useLiveField((state) => state.jobError);
}

/** The project the current job was started for, before the backend resolves it. */
export function useLiveStartedProject() {
  return useLiveField((state) => state.startedProject);
}

/** The topbar's run progress: `{ dimension, percent }`, or null when idle. */
export function useLiveProgress() {
  return useLiveField((state) => state.progress);
}

/** Whether a run is in flight. Flips once per run, not once per tick. */
export function useIsEvaluating() {
  return useLiveField((state) => state.isEvaluating);
}

/**
 * Live findings for one dimension, or every dimension keyed by name when
 * `dimension` is omitted.
 */
export function useLiveFindings(dimension) {
  return useLiveField((state) => (
    dimension ? (state.liveViolations[dimension] || EMPTY_DIMENSION_FINDINGS) : state.liveViolations
  ));
}

/** Start, dismiss and cancel. Stable across renders and safe to pass as props. */
export function useEvaluationActions() {
  return useContext(EvaluationLiveContext)?.actions || NO_ACTIONS;
}

// The topbar chip and hairline read the same progress query the stat strip
// and the progress bar do, so following a run from any page costs no extra
// polling.
function useTopbarRunProgress(job, isEvaluating) {
  const { data } = useEvaluationProgress(isEvaluating ? job?.jobId : undefined, !isEvaluating);
  return useMemo(() => {
    if (!isEvaluating) return null;
    const overall = computeOverallProgress(data);
    const runningDim = (data?.dimensions || []).find((d) => d?.state === DIM_STATE.RUNNING);
    return {
      dimension: runningDim?.id ? String(runningDim.id).toLowerCase() : null,
      percent: overall.totalFiles > 0 ? overall.overallPct : null,
    };
  }, [isEvaluating, data]);
}

// Published after the commit rather than during render: a subscriber that
// mounted in this same commit is already listening by the time the values
// reach the store.
function usePublishLiveEvaluation(store, lifecycle, progress, isEvaluating) {
  useLayoutEffect(() => {
    store.setHandlers({
      start: lifecycle.handleStartEvaluation,
      dismiss: lifecycle.handleEvalDismiss,
      cancel: lifecycle.cancelEvaluation,
    });
    store.publish({
      job: lifecycle.job,
      jobError: lifecycle.jobError,
      liveViolations: lifecycle.liveViolations || EMPTY_FINDINGS,
      startedProject: lifecycle.startedProject,
      progress,
      isEvaluating,
    });
  });
}

/** Supplies an existing store to the tree without owning the lifecycle. */
export function EvaluationLiveStoreProvider({ store, children }) {
  return (
    <EvaluationLiveContext.Provider value={store}>
      {children}
    </EvaluationLiveContext.Provider>
  );
}

/**
 * Owns the evaluation lifecycle and publishes it to the store.
 *
 * `children` is passed through untouched, so a tick that re-renders this
 * provider does not re-render the app below it.
 */
export function EvaluationLiveProvider({ store, navigation, projects, selectedProject, children }) {
  const lifecycle = useEvaluationLifecycle({ navigation, projects, selectedProject });
  const isEvaluating = lifecycle.job?.status === JOB_STATUS.RUNNING;
  const progress = useTopbarRunProgress(lifecycle.job, isEvaluating);
  usePublishLiveEvaluation(store, lifecycle, progress, isEvaluating);
  return <EvaluationLiveStoreProvider store={store}>{children}</EvaluationLiveStoreProvider>;
}
