import { useEffect, useRef, useState } from 'react';
import { startEvaluation, getEvaluation, cancelEvaluation, getDimensionEval, listEvaluations } from '../../../api/index.js';

const DIMENSION_POLL_MS = 2000;
const JOB_POLL_MS = 1500;
const MAX_DIM_POLL_FAILURES = 10;

function stopTimer(ref) {
  if (ref.current) {
    clearInterval(ref.current);
    ref.current = null;
  }
}

async function pollSingleDimension(dim, project, runId, refs, setLiveViolations) {
  try {
    const data = await getDimensionEval(project, runId, dim);
    refs.dimFailCount[dim] = 0;
    if (data?.violations) {
      setLiveViolations(prev => ({ ...prev, [dim]: data.violations }));
      if (!data.partial) {
        refs.partialDimensions.delete(dim);
      }
    }
  } catch (err) {
    console.debug('Dimension poll failed:', dim, err);
    const fails = (refs.dimFailCount[dim] || 0) + 1;
    refs.dimFailCount[dim] = fails;
    if (fails > MAX_DIM_POLL_FAILURES) refs.partialDimensions.delete(dim);
  }
}

function handleJobUpdate(updated, refs, setJob, callbacks) {
  setJob((prev) => ({ ...updated, repo: prev?.repo }));
  if (updated.dimensions?.length && !refs.requestedDimensions.length) {
    refs.requestedDimensions = updated.dimensions;
  }
  if (updated.phase === 'analyzing' && updated.currentDimension) {
    refs.partialDimensions.add(updated.currentDimension);
  }
  const hasOutput = updated.outputProject && updated.outputRunId;
  const isAnalyzing = updated.phase === 'analyzing' || updated.phase === 'scoring' || updated.status !== 'running';
  const canPollDims = hasOutput && isAnalyzing;
  if (updated.status !== 'running') {
    callbacks.stopPolling();
    if (canPollDims && !refs.dimPollingStarted) {
      refs.dimPollingStarted = true;
      callbacks.startDimPolling(updated.outputProject, updated.outputRunId);
    }
  } else if (canPollDims && !refs.dimPollingStarted) {
    refs.dimPollingStarted = true;
    callbacks.startDimPolling(updated.outputProject, updated.outputRunId);
  }
}

export function useEvaluation() {
  const [job, setJob] = useState(null);
  const [jobError, setJobError] = useState('');
  const [liveViolations, setLiveViolations] = useState({});

  const pollRef = useRef(null);
  const dimPollRef = useRef(null);
  const requestedDimensionsRef = useRef([]);
  const liveViolationsRef = useRef({});
  const partialDimensionsRef = useRef(new Set());
  const dimFailCountRef = useRef({});

  useEffect(() => {
    listEvaluations()
      .then((jobs) => {
        const running = jobs.find((j) => j.status === 'running');
        if (running) {
          setJob(running);
          startPolling(running.jobId);
        }
      })
      .catch((err) => console.warn('Failed to fetch running evaluations:', err));
    return () => {
      stopTimer(pollRef);
      stopTimer(dimPollRef);
    };
  }, []);

  useEffect(() => {
    liveViolationsRef.current = liveViolations;
  }, [liveViolations]);

  function startDimensionPolling(project, runId) {
    stopTimer(dimPollRef);
    dimFailCountRef.current = {};
    const refs = { dimFailCount: dimFailCountRef.current, partialDimensions: partialDimensionsRef.current };
    dimPollRef.current = setInterval(async () => {
      const partial = [...partialDimensionsRef.current];
      if (!partial.length) return;
      await Promise.allSettled(
        partial.map((dim) => pollSingleDimension(dim, project, runId, refs, setLiveViolations))
      );
    }, DIMENSION_POLL_MS);
  }

  function startPolling(jobId) {
    stopTimer(pollRef);
    const refs = {
      requestedDimensions: requestedDimensionsRef.current,
      partialDimensions: partialDimensionsRef.current,
      dimPollingStarted: false,
    };
    const callbacks = {
      stopPolling: () => stopTimer(pollRef),
      startDimPolling: startDimensionPolling,
    };
    pollRef.current = setInterval(async () => {
      try {
        const updated = await getEvaluation(jobId);
        handleJobUpdate(updated, refs, setJob, callbacks);
      } catch (err) {
        setJob((prev) => prev ? { ...prev, status: 'lost' } : prev);
        setJobError(err.message);
        stopTimer(pollRef);
        stopTimer(dimPollRef);
      }
    }, JOB_POLL_MS);
  }

  async function startEvaluationJob(payload) {
    setJobError('');
    const rawDims = payload.dimensions ?? [];
    requestedDimensionsRef.current = typeof rawDims === 'string'
      ? rawDims.split(',').map(d => d.trim()).filter(Boolean)
      : rawDims;
    liveViolationsRef.current = {};
    partialDimensionsRef.current = new Set();
    setLiveViolations({});
    const maxSubagents = parseInt(localStorage.getItem('cc-max-subagents') || '5', 10);
    if (maxSubagents !== 5) payload.maxSubagents = maxSubagents;
    const poolBudget = parseInt(localStorage.getItem('cc-pool-budget') || '600', 10);
    if (poolBudget !== 600) payload.poolBudget = poolBudget;
    try {
      const created = await startEvaluation(payload);
      setJob({ ...created, repo: payload.repo });
      startPolling(created.jobId);
    } catch (err) {
      setJobError(err.message);
    }
  }

  function clearJob() {
    stopTimer(pollRef);
    stopTimer(dimPollRef);
    setJob(null);
    setJobError('');
    setLiveViolations({});
    liveViolationsRef.current = {};
    requestedDimensionsRef.current = [];
    partialDimensionsRef.current = new Set();
    dimFailCountRef.current = {};
  }

  async function cancelEvaluationJob() {
    if (!job?.jobId) return;
    try {
      await cancelEvaluation(job.jobId);
      clearJob();
    } catch (err) {
      setJobError(err.message);
    }
  }

  return { job, jobError, liveViolations, startEvaluation: startEvaluationJob, clearJob, cancelEvaluation: cancelEvaluationJob };
}
