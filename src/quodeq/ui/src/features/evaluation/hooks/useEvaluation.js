import { useEffect, useRef, useState } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { ACTIVE_PROVIDER_KEY, providerKey, DEFAULT_MAX_SUBAGENTS, DEFAULT_POOL_BUDGET } from '../../../constants.js';
import { confirmDialog } from '../../../utils/confirmDialog.js';

const DIMENSION_POLL_INITIAL_MS = 2000;
const DIMENSION_POLL_MAX_MS = 8000;
const JOB_POLL_INITIAL_MS = 1500;
const MAX_DIM_POLL_FAILURES = 10;
const POLL_CONCURRENCY = 4;
const POLL_BACKOFF_FACTOR = 1.5;
const DEFAULT_OLLAMA_SUBAGENTS = '1';
const DEFAULT_CLI_SUBAGENTS = String(DEFAULT_MAX_SUBAGENTS);
const DEFAULT_OLLAMA_BUDGET = '0';
const DEFAULT_CLI_BUDGET = String(DEFAULT_POOL_BUDGET);

function stopTimer(ref) {
  if (ref.current) {
    clearInterval(ref.current);
    ref.current = null;
  }
}

async function pollSingleDimension(dim, project, runId, refs, setLiveViolations, getDimensionEval) {
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
  // Seed partialDimensions on reconnect. When the dashboard is restarted
  // while a scan is running, the CLI-launched job reports phase=analyzing
  // but currentDimension is often null (the pipeline-level phase setter
  // does not know which dimension the worker pool is on right now), so
  // the block above adds nothing to partialDimensions. Without any
  // dimensions queued, startDimPolling spins with no work and the Live
  // Violations panel stays empty. If we're analyzing and know the list
  // of requested dimensions, seed them all — pollSingleDimension will
  // remove each one from the set as soon as its status comes back
  // non-partial.
  if (isAnalyzing
      && refs.partialDimensions.size === 0
      && refs.requestedDimensions.length) {
    for (const dim of refs.requestedDimensions) {
      refs.partialDimensions.add(dim);
    }
  }
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

async function pollPartialDimensions(partialDimensionsRef, project, runId, refs, setLiveViolations, getDimensionEval) {
  const partial = [...partialDimensionsRef.current];
  if (!partial.length) return false;
  let hadErrors = false;
  for (let i = 0; i < partial.length; i += POLL_CONCURRENCY) {
    const batch = partial.slice(i, i + POLL_CONCURRENCY);
    const results = await Promise.allSettled(
      batch.map((dim) => pollSingleDimension(dim, project, runId, refs, setLiveViolations, getDimensionEval))
    );
    if (results.some((r) => r.status === 'rejected')) hadErrors = true;
  }
  return hadErrors;
}

function createDimensionPoller(dimPollRef, dimFailCountRef, partialDimensionsRef, setLiveViolations, getDimensionEval) {
  return function startDimensionPolling(project, runId) {
    stopTimer(dimPollRef);
    dimFailCountRef.current = {};
    let delay = DIMENSION_POLL_INITIAL_MS;
    const refs = { dimFailCount: dimFailCountRef.current, partialDimensions: partialDimensionsRef.current };
    function scheduleNext() {
      dimPollRef.current = setTimeout(async () => {
        const anyFailed = await pollPartialDimensions(partialDimensionsRef, project, runId, refs, setLiveViolations, getDimensionEval);
        delay = anyFailed ? Math.min(delay * POLL_BACKOFF_FACTOR, DIMENSION_POLL_MAX_MS) : DIMENSION_POLL_INITIAL_MS;
        scheduleNext();
      }, delay);
    }
    scheduleNext();
  };
}

function createJobPoller(refs, setters, startDimensionPolling, getEvaluation) {
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
        console.error('Poll error:', err);
        setJobError('Evaluation polling failed');
        stopTimer(pollRef);
        stopTimer(dimPollRef);
      }
    }, JOB_POLL_INITIAL_MS);
  };
}

/**
 * Build the evaluation payload from provider settings.
 * Throws if the orchestrator model is not configured.
 */
function preparePayload(payload, storage = localStorage) {
  const activeProvider = storage.getItem(ACTIVE_PROVIDER_KEY) || '';
  if (!activeProvider) throw new Error('No provider selected. Go to Settings to configure one.');

  const get = (key) => storage.getItem(providerKey(activeProvider, key));

  const model = get('model');
  if (!model) throw new Error('No model selected. Go to Settings and select one.');

  const defaultSubagents = ['ollama'].includes(activeProvider) ? DEFAULT_OLLAMA_SUBAGENTS : DEFAULT_CLI_SUBAGENTS;
  const subagents = parseInt(get('subagents') || defaultSubagents, 10);

  const defaultBudget = ['ollama'].includes(activeProvider) ? DEFAULT_OLLAMA_BUDGET : DEFAULT_CLI_BUDGET;
  const poolBudget = parseInt(get('pool-budget') || defaultBudget, 10);

  const result = {
    ...payload,
    aiCmd: activeProvider,
    aiModel: model,
    maxSubagents: subagents,
    poolBudget,
  };
  if (get('per-dimension') === 'true') result.perDimension = true;
  if (get('verify') === 'false') result.verifyFindings = false;
  return result;
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

function useResumeRunning(setJob, startPolling, pollRef, dimPollRef, listEvaluations) {
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
  }, []); // eslint-disable-line react-hooks/exhaustive-deps -- mount-only: resume any running eval; startPolling is stable (defined outside render cycle via refs)
}

function useJobLifecycle(refs, setJob, setJobError, setLiveViolations, startPolling, { startEvaluation, cancelEvaluation }) {
  async function startEvaluationJob(payload) {
    setJobError('');
    refs.requestedDimensionsRef.current = parseDimensions(payload);
    refs.liveViolationsRef.current = {};
    refs.partialDimensionsRef.current = new Set();
    setLiveViolations({});
    try {
      if (Array.isArray(payload.dimensions) && payload.dimensions.length === 0) {
        throw new Error('Select at least one dimension.');
      }
      const prepared = preparePayload(payload);
      const created = await startEvaluation(prepared);
      setJob({ ...created, repo: prepared.repo });
      startPolling(created.jobId);
    } catch (err) {
      console.error('Start error:', err);
      setJobError(err.message?.startsWith('No ') || err.message?.startsWith('Select ') ? err.message : 'Failed to start evaluation');
    }
  }

  function clearJob() {
    stopTimer(refs.pollRef); stopTimer(refs.dimPollRef);
    setJob(null); setJobError(''); setLiveViolations({});
    resetRefs(refs.liveViolationsRef, refs.requestedDimensionsRef, refs.partialDimensionsRef, refs.dimFailCountRef);
  }

  async function cancelEvaluationJob(jobId) {
    if (!jobId) return;
    const ok = await confirmDialog({
      title: 'Cancel evaluation?',
      message: 'Stop the running scan. Any findings collected so far will still be saved.',
      confirmLabel: 'Cancel evaluation',
      cancelLabel: 'Keep running',
      variant: 'danger',
    });
    if (!ok) return;
    try {
      await cancelEvaluation(jobId);
      clearJob();
    } catch (err) {
      console.error('Cancel error:', err);
      setJobError('Failed to cancel evaluation');
    }
  }

  return { startEvaluationJob, clearJob, cancelEvaluationJob };
}

function usePollingSetup(refs, setJob, setJobError, setLiveViolations, { getDimensionEval, getEvaluation, listEvaluations }) {
  const startDimensionPolling = createDimensionPoller(refs.dimPollRef, refs.dimFailCountRef, refs.partialDimensionsRef, setLiveViolations, getDimensionEval);
  const startPolling = createJobPoller(
    { poll: refs.pollRef, dimPoll: refs.dimPollRef, requestedDimensions: refs.requestedDimensionsRef, partialDimensions: refs.partialDimensionsRef },
    { setJob, setJobError },
    startDimensionPolling,
    getEvaluation,
  );
  useResumeRunning(setJob, startPolling, refs.pollRef, refs.dimPollRef, listEvaluations);
  return startPolling;
}

export function useEvaluation() {
  const api = useApi();
  const { startEvaluation, getEvaluation, cancelEvaluation, getDimensionEval, listEvaluations } = api;
  const [job, setJob] = useState(null);
  const [jobError, setJobError] = useState('');
  const [liveViolations, setLiveViolations] = useState({});
  const refs = useEvalRefs();
  const startPolling = usePollingSetup(refs, setJob, setJobError, setLiveViolations, { getDimensionEval, getEvaluation, listEvaluations });
  useEffect(() => { refs.liveViolationsRef.current = liveViolations; }, [liveViolations]);

  const { startEvaluationJob, clearJob, cancelEvaluationJob } = useJobLifecycle(refs, setJob, setJobError, setLiveViolations, startPolling, { startEvaluation, cancelEvaluation });

  return {
    job, jobError, liveViolations,
    startEvaluation: startEvaluationJob,
    clearJob,
    cancelEvaluation: () => cancelEvaluationJob(job?.jobId),
  };
}
