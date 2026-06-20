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
export function useEvaluationLifecycle({ settings, navigation, projects, storage: _storage }) {
  const storage = _storage || localStorage;
  const { navTab, navReset } = navigation;
  const { loadProjects, setProjects, selectProjectAndRun } = projects;
  const { job, jobError, liveViolations, startEvaluation, clearJob, cancelEvaluation } = useEvaluation();

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
      selectProjectAndRun(job.outputProject, job.outputRunId);
    }
    prevJobRef.current = job;
  }, [job]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleStartEvaluation(payload) {
    // Hard guard: only one evaluation may run at a time. A second start
    // request (e.g. user clicked through the onboarding wizard while a
    // re-evaluation was already in flight on a different project) would
    // otherwise overwrite the live job state and confuse the lifecycle.
    if (job && job.status === 'running') {
      console.warn('[evaluation] start request ignored — a job is already running');
      return;
    }
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
    startEvaluation({ ...payload, subagentModel });
  }

  function handleEvalDismiss(action) {
    if (action === 'view') {
      navReset();
    }
    clearJob();
  }

  const activeProvider = storage.getItem(ACTIVE_PROVIDER_KEY) || '';
  const isLocalApi = LOCAL_API_PROVIDERS.has(activeProvider);

  return {
    job, jobError, liveViolations,
    analysisPower, setAnalysisPower, persistAnalysisPower,
    handleStartEvaluation, handleEvalDismiss, cancelEvaluation,
    isLocalApi,
  };
}
