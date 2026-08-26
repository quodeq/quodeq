import { useState, useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useEvaluation, LOCAL_API_PROVIDERS } from '../features/evaluation/hooks/useEvaluation.js';
import { getLevels, STORAGE_KEY as POWER_KEY } from '../features/evaluation/components/powerLevels.js';
import { ACTIVE_PROVIDER_KEY, providerKey } from '../constants.js';
import { projectKeys } from '../api/queryKeys.js';
import { t } from '../strings/index.js';

const TIER_NAMES = ['fast', 'balanced', 'thorough'];
const DEFAULT_ANALYSIS_POWER = 2;

/**
 * Manages the full evaluation lifecycle: start, poll, dismiss, cancel.
 *
 * Extracts evaluation-specific state and side effects from App so that
 * App only wires the hook's return values into the component tree.
 */
export function useEvaluationLifecycle({ settings, navigation, projects, selectedProject = null, storage: _storage }) {
  const storage = _storage || localStorage;
  const { navTab, navReset } = navigation;
  const { loadProjects, setProjects, selectProjectAndRun } = projects;
  const { job, jobError, liveViolations, startEvaluation, clearJob, cancelEvaluation, startedProject } = useEvaluation();
  const queryClient = useQueryClient();
  // Set when a start request is refused because another evaluation is
  // already running. Surfaced through jobError so the Evaluate screen's
  // toast shows it; a silent refusal left users believing the visible
  // (older) evaluation was the one they just launched.
  const [blockedStartError, setBlockedStartError] = useState(null);

  // Storage reads degrade to '' when the backing store throws (private
  // mode, disabled storage) instead of crashing the caller, matching the
  // guarded reads below.
  const safeGetItem = (key) => {
    try { return storage.getItem(key) || ''; } catch (e) { console.warn('localStorage unavailable:', e); return ''; }
  };

  const [analysisPower, setAnalysisPower] = useState(() => {
    try { return Number(storage.getItem(POWER_KEY)) || DEFAULT_ANALYSIS_POWER; } catch (e) { console.warn('localStorage unavailable:', e); return DEFAULT_ANALYSIS_POWER; }
  });

  function persistAnalysisPower(level) {
    try { storage.setItem(POWER_KEY, String(level)); } catch (e) { console.warn('localStorage unavailable:', e); }
  }

  const prevJobRef = useRef(null);
  const refreshedRunRef = useRef(null);
  useEffect(() => {
    if (job?.status === 'running' && !prevJobRef.current) navTab('evaluate');
    // Auto-refresh dashboard data as soon as the run completes
    const finished = job && job.status !== 'running' && job.outputProject && job.outputRunId;
    if (finished && refreshedRunRef.current !== job.outputRunId) {
      refreshedRunRef.current = job.outputRunId;
      loadProjects()
        .then((list) => setProjects(list))
        .catch((err) => console.error('Failed to refresh projects:', err));
      // useAppState's dashboard-key effect (removed as redundant: the
      // selectProjectAndRun call below mints a new dashboard query key on its
      // own) only ever covered the dashboard side. The scores side has its
      // own key -- projectKeys.scores(project, null, source), the `latest`
      // query in useProjectScores -- and it does NOT change when selectedRun
      // flips, because `asOf` only resolves to the new run once
      // `availableRuns` (itself sourced from this same query) already lists
      // it. Left un-invalidated, a user parked on the Overview when a run
      // completes never gets the refreshed `availableRuns`/`accumulated`:
      // repeat-run projects show stale grades until a tab round-trip, and a
      // first-run project never gets `accumulated`, so `contentReady` stays
      // false and the page sits on the inline loader indefinitely. Evaluations
      // only ever write to the
      // local repo, so the 'local' source (the default) is always correct
      // here regardless of which source tab the user has open elsewhere.
      // Unconditional on outputProject: invalidating an inactive observer's
      // query just marks it stale (no fetch), so this is a harmless no-op
      // when nobody is looking at that project.
      queryClient.invalidateQueries({ queryKey: projectKeys.scores(job.outputProject, null, 'local') });
      // The Compare tab holds one slim summary per project; without this a
      // finished run on ANY project leaves its fleet row stale until the
      // staleTime expires or the tab remounts. Same harmless-no-op rule as
      // above when Compare isn't mounted.
      queryClient.invalidateQueries({ queryKey: projectKeys.compareSummary(job.outputProject, 'local') });
      // Only move the selection to the finished run when the user is
      // already on that project (or has none selected, e.g. first-eval
      // onboarding). Unconditional switching yanked a user browsing
      // project B into project A the moment A's background run finished,
      // without any nav reset. The evaluate card's "view results" button
      // remains the explicit way to jump to another project's results.
      if (!selectedProject || job.outputProject === selectedProject) {
        selectProjectAndRun(job.outputProject, job.outputRunId);
      }
    }
    prevJobRef.current = job;
  }, [job]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleStartEvaluation(payload) {
    // Hard guard: only one evaluation may run at a time. A second start
    // request (e.g. user clicked through the onboarding wizard while a
    // re-evaluation was already in flight on a different project) would
    // otherwise overwrite the live job state and confuse the lifecycle.
    // Returns false so callers can keep one-shot UI state (the clean-scan
    // "once" toggle) instead of consuming it for a start that never ran.
    if (job && job.status === 'running') {
      setBlockedStartError(
        t('evaluate.alreadyRunning'),
      );
      return false;
    }
    setBlockedStartError(null);
    const activeProvider = safeGetItem(ACTIVE_PROVIDER_KEY);
    const get = (key) => safeGetItem(providerKey(activeProvider, key));
    // Ollama uses a single analysis model; CLI providers use tier-based selection.
    // Falls back to the orchestrator model if no analysis-specific model is set.
    const analysisModel = get('model-analysis');
    let subagentModel;
    if (analysisModel) {
      subagentModel = analysisModel;
    } else {
      subagentModel = get(`model-${TIER_NAMES[analysisPower - 1]}`) || get('model') || undefined;
    }
    // Swallow the rejection on the copy we discard: startMutation's onError
    // already surfaces failures via jobError. Callers get the original
    // promise so they can react to success/failure themselves.
    const started = startEvaluation({ ...payload, subagentModel });
    Promise.resolve(started).catch(() => {});
    return started;
  }

  function handleEvalDismiss(action) {
    if (action === 'view') {
      // The completion effect deliberately leaves the selection alone when
      // the user browsed to another project mid-run; this button is the
      // explicit jump to the evaluated project's results. Prefer the job's
      // resolved project, fall back to the one it was started for.
      const target = job?.outputProject || startedProject || null;
      if (target && target !== selectedProject) {
        selectProjectAndRun(target, job?.outputRunId || null);
      }
      navReset();
    }
    setBlockedStartError(null);
    clearJob();
  }

  const activeProvider = safeGetItem(ACTIVE_PROVIDER_KEY);
  const isLocalApi = LOCAL_API_PROVIDERS.has(activeProvider);

  return {
    job, jobError: jobError || blockedStartError, liveViolations,
    analysisPower, setAnalysisPower, persistAnalysisPower,
    handleStartEvaluation, handleEvalDismiss, cancelEvaluation,
    isLocalApi, startedProject,
  };
}
