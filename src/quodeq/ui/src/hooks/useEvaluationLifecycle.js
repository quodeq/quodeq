import { useState, useEffect, useRef } from 'react';
import { useEvaluation } from '../features/evaluation/hooks/useEvaluation.js';
import { getLevels, STORAGE_KEY as POWER_KEY } from '../features/evaluation/components/powerLevels.js';

/**
 * Manages the full evaluation lifecycle: start, poll, dismiss, cancel.
 *
 * Extracts evaluation-specific state and side effects from App so that
 * App only wires the hook's return values into the component tree.
 */
export function useEvaluationLifecycle({ settings, navigation, projects }) {
  const { navTab, navReset } = navigation;
  const { loadProjects, setProjects, selectProjectAndRun } = projects;
  const { job, jobError, liveViolations, startEvaluation, clearJob, cancelEvaluation } = useEvaluation();

  const [analysisPower, setAnalysisPower] = useState(() => {
    try { return Number(localStorage.getItem(POWER_KEY)) || 2; } catch (e) { console.warn('localStorage unavailable:', e); return 2; }
  });

  const prevJobRef = useRef(null);
  useEffect(() => {
    if (job?.status === 'running' && !prevJobRef.current) navTab('evaluate');
    prevJobRef.current = job;
  }, [job]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleStartEvaluation(payload) {
    const levels = getLevels();
    const subagentModel = levels.find(l => l.level === analysisPower)?.model;
    startEvaluation({ ...payload, aiCmd: settings.aiCmd || undefined, aiModel: settings.aiModel || undefined, subagentModel, verifyFindings: settings.verifyFindings });
  }

  function handleEvalDismiss(action) {
    if (action === 'view') {
      const project = job?.outputProject;
      const runId = job?.outputRunId;
      if (project) {
        loadProjects()
          .then((list) => setProjects(list))
          .catch((err) => console.error('Operation failed:', err));
        selectProjectAndRun(project, runId);
      }
      navReset();
    }
    clearJob();
  }

  return {
    job, jobError, liveViolations,
    analysisPower, setAnalysisPower,
    handleStartEvaluation, handleEvalDismiss, cancelEvaluation,
  };
}
