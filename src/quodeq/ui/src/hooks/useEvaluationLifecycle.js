import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useEvaluation, LOCAL_API_PROVIDERS } from '../features/evaluation/hooks/useEvaluation.js';
import { ACTIVE_PROVIDER_KEY, providerKey } from '../constants.js';
import { safeGetItem, readAnalysisPower, writeAnalysisPower, resolveSubagentModel } from './evaluationLifecycleHelpers.js';
import { useJobCompletionEffect } from './useJobCompletionEffect.js';
import { t } from '../strings/index.js';

/**
 * Manages the full evaluation lifecycle: start, poll, dismiss, cancel.
 *
 * Extracts evaluation-specific state and side effects from App so that
 * App only wires the hook's return values into the component tree.
 *
 * Split into evaluationLifecycleHelpers.js (storage read/write, subagent-
 * model resolution) and hooks/useJobCompletionEffect.js (the on-completion
 * effect) -- this file composes the two and owns the start/dismiss handlers.
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

  const [analysisPower, setAnalysisPower] = useState(() => readAnalysisPower(storage));

  function persistAnalysisPower(level) {
    writeAnalysisPower(storage, level);
  }

  useJobCompletionEffect({ job, navTab, loadProjects, setProjects, queryClient, selectedProject, selectProjectAndRun });

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
    const activeProvider = safeGetItem(storage, ACTIVE_PROVIDER_KEY);
    const get = (key) => safeGetItem(storage, providerKey(activeProvider, key));
    const subagentModel = resolveSubagentModel({ get, analysisPower });
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

  const activeProvider = safeGetItem(storage, ACTIVE_PROVIDER_KEY);
  const isLocalApi = LOCAL_API_PROVIDERS.has(activeProvider);

  return {
    job, jobError: jobError || blockedStartError, liveViolations,
    analysisPower, setAnalysisPower, persistAnalysisPower,
    handleStartEvaluation, handleEvalDismiss, cancelEvaluation,
    isLocalApi, startedProject,
  };
}
