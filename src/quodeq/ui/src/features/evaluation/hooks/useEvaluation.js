import { useEffect, useRef, useState } from 'react';
import { startEvaluation, getEvaluation, cancelEvaluation, getDimensionEval, listEvaluations } from '../../../api/index.js';
import { DEFAULT_MAX_SUBAGENTS, DEFAULT_POOL_BUDGET, SUBAGENTS_STORAGE_KEY, POOL_BUDGET_STORAGE_KEY } from '../../../constants.js';

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

function createDimensionPoller(dimPollRef, dimFailCountRef, partialDimensionsRef, setLiveViolations) {
  return function startDimensionPolling(project, runId) {
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
  };
}

function createJobPoller(refs, setters, startDimensionPolling) {
  const { poll: pollRef, dimPoll: dimPollRef, requestedDimensions: requestedDimensionsRef, partialDimensions: partialDimensionsRef } = refs;
  const { setJob, setJobError } = setters;
  return function startPolling(jobId) {
    stopTimer(pollRef);
    const localRefs = {
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
        handleJobUpdate(updated, localRefs, setJob, callbacks);
      } catch (err) {
        setJob((prev) => prev ? { ...prev, status: 'lost' } : prev);
        setJobError(err.message);
        stopTimer(pollRef);
        stopTimer(dimPollRef);
      }
    }, JOB_POLL_MS);
  };
}

function preparePayload(payload, storage = localStorage) {
  const maxSubagents = parseInt(storage.getItem(SUBAGENTS_STORAGE_KEY) || String(DEFAULT_MAX_SUBAGENTS), 10);
  if (maxSubagents !== DEFAULT_MAX_SUBAGENTS) payload.maxSubagents = maxSubagents;
  const poolBudget = parseInt(storage.getItem(POOL_BUDGET_STORAGE_KEY) || String(DEFAULT_POOL_BUDGET), 10);
  if (poolBudget !== DEFAULT_POOL_BUDGET) payload.poolBudget = poolBudget;
}

function parseDimensions(payload) {
  const rawDims = payload.dimensions ?? [];
  return typeof rawDims === 'string' ? rawDims.split(',').map(d => d.trim()).filter(Boolean) : rawDims;
}

function resetRefs(liveViolationsRef, requestedDimensionsRef, partialDimensionsRef, dimFailCountRef) {
  liveViolationsRef.current = {};
  requestedDimensionsRef.current = [];
  partialDimensionsRef.current = new Set();
  dimFailCountRef.current = {};
}

function useEvalRefs() {
  return {
    pollRef: useRef(null),
    dimPollRef: useRef(null),
    requestedDimensionsRef: useRef([]),
    liveViolationsRef: useRef({}),
    partialDimensionsRef: useRef(new Set()),
    dimFailCountRef: useRef({}),
  };
}

function useResumeRunning(setJob, startPolling, pollRef, dimPollRef) {
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
}

function useJobLifecycle(refs, setJob, setJobError, setLiveViolations, startPolling) {
  async function startEvaluationJob(payload) {
    setJobError('');
    refs.requestedDimensionsRef.current = parseDimensions(payload);
    refs.liveViolationsRef.current = {};
    refs.partialDimensionsRef.current = new Set();
    setLiveViolations({});
    preparePayload(payload);
    try {
      const created = await startEvaluation(payload);
      setJob({ ...created, repo: payload.repo });
      startPolling(created.jobId);
    } catch (err) {
      setJobError(err.message);
    }
  }

  function clearJob() {
    stopTimer(refs.pollRef); stopTimer(refs.dimPollRef);
    setJob(null); setJobError(''); setLiveViolations({});
    resetRefs(refs.liveViolationsRef, refs.requestedDimensionsRef, refs.partialDimensionsRef, refs.dimFailCountRef);
  }

  async function cancelEvaluationJob(jobId) {
    if (!jobId) return;
    try {
      await cancelEvaluation(jobId);
      clearJob();
    } catch (err) {
      setJobError(err.message);
    }
  }

  return { startEvaluationJob, clearJob, cancelEvaluationJob };
}

function usePollingSetup(refs, setJob, setJobError, setLiveViolations) {
  const startDimensionPolling = createDimensionPoller(refs.dimPollRef, refs.dimFailCountRef, refs.partialDimensionsRef, setLiveViolations);
  const startPolling = createJobPoller(
    { poll: refs.pollRef, dimPoll: refs.dimPollRef, requestedDimensions: refs.requestedDimensionsRef, partialDimensions: refs.partialDimensionsRef },
    { setJob, setJobError },
    startDimensionPolling,
  );
  useResumeRunning(setJob, startPolling, refs.pollRef, refs.dimPollRef);
  return startPolling;
}

export function useEvaluation() {
  const [job, setJob] = useState(null);
  const [jobError, setJobError] = useState('');
  const [liveViolations, setLiveViolations] = useState({});
  const refs = useEvalRefs();
  const startPolling = usePollingSetup(refs, setJob, setJobError, setLiveViolations);
  useEffect(() => { refs.liveViolationsRef.current = liveViolations; }, [liveViolations]);

  const { startEvaluationJob, clearJob, cancelEvaluationJob } = useJobLifecycle(refs, setJob, setJobError, setLiveViolations, startPolling);

  return {
    job, jobError, liveViolations,
    startEvaluation: startEvaluationJob,
    clearJob,
    cancelEvaluation: () => cancelEvaluationJob(job?.jobId),
  };
}
