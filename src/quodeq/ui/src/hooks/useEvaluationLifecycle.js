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

  function persistAnalysisPower(level) {
    try { localStorage.setItem(POWER_KEY, String(level)); } catch (e) { console.warn('localStorage unavailable:', e); }
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
    const levels = getLevels();
    const subagentModel = levels.find(l => l.level === analysisPower)?.model;
    startEvaluation({ ...payload, aiCmd: settings.aiCmd || undefined, aiModel: settings.aiModel || undefined, subagentModel, verifyFindings: settings.verifyFindings });
  }

  function handleEvalDismiss(action) {
    if (action === 'view') {
      navReset();
    }
    clearJob();
  }

  return {
    job, jobError, liveViolations,
    analysisPower, setAnalysisPower, persistAnalysisPower,
    handleStartEvaluation, handleEvalDismiss, cancelEvaluation,
  };
}
