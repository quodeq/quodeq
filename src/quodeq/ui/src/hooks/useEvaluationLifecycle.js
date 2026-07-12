import { useState, useEffect, useRef } from 'react';
import { useEvaluation, LOCAL_API_PROVIDERS } from '../features/evaluation/hooks/useEvaluation.js';
import { getLevels, STORAGE_KEY as POWER_KEY } from '../features/evaluation/components/powerLevels.js';
import { ACTIVE_PROVIDER_KEY, providerKey } from '../constants.js';

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
  // Set when a start request is refused because another evaluation is
  // already running. Surfaced through jobError so the Evaluate screen's
  // toast shows it; a silent refusal left users believing the visible
  // (older) evaluation was the one they just launched.
  const [blockedStartError, setBlockedStartError] = useState(null);

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
        'An evaluation is already running. Cancel it or wait for it to finish.',
      );
      return false;
    }
    setBlockedStartError(null);
    const activeProvider = storage.getItem(ACTIVE_PROVIDER_KEY) || '';
    const get = (key) => storage.getItem(providerKey(activeProvider, key));
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
      navReset();
    }
    setBlockedStartError(null);
    clearJob();
  }

  const activeProvider = storage.getItem(ACTIVE_PROVIDER_KEY) || '';
  const isLocalApi = LOCAL_API_PROVIDERS.has(activeProvider);

  return {
    job, jobError: jobError || blockedStartError, liveViolations,
    analysisPower, setAnalysisPower, persistAnalysisPower,
    handleStartEvaluation, handleEvalDismiss, cancelEvaluation,
    isLocalApi, startedProject,
  };
}
