import { useEffect, useRef, useState } from 'react';
import { startEvaluation, getEvaluation, cancelEvaluation, getDimensionEval, listEvaluations } from '../../../api/index.js';

const DIMENSION_POLL_MS = 2000;
const JOB_POLL_MS = 1500;
const MAX_DIM_POLL_FAILURES = 10;

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
    // Discover any running evaluation (e.g. started in another tab)
    listEvaluations()
      .then((jobs) => {
        const running = jobs.find((j) => j.status === 'running');
        if (running) {
          setJob(running);
          startPolling(running.jobId);
        }
      })
      .catch(() => {});
    return () => {
      stopPolling();
      stopDimensionPolling();
    };
  }, []);

  useEffect(() => {
    liveViolationsRef.current = liveViolations;
  }, [liveViolations]);


  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  function stopDimensionPolling() {
    if (dimPollRef.current) {
      clearInterval(dimPollRef.current);
      dimPollRef.current = null;
    }
  }

  function startDimensionPolling(project, runId) {
    stopDimensionPolling();
    dimFailCountRef.current = {};
    dimPollRef.current = setInterval(async () => {
      // Only poll dimensions that are still partial (stream-based)
      const partial = [...partialDimensionsRef.current];
      if (!partial.length) return;

      await Promise.allSettled(
        partial.map(async (dim) => {
          try {
            const data = await getDimensionEval(project, runId, dim);
            dimFailCountRef.current[dim] = 0;
            if (data?.violations) {
              setLiveViolations(prev => ({ ...prev, [dim]: data.violations }));
              if (!data.partial) {
                // Final scored result — stop polling this dimension
                partialDimensionsRef.current.delete(dim);
              }
            }
          } catch {
            const fails = (dimFailCountRef.current[dim] || 0) + 1;
            dimFailCountRef.current[dim] = fails;
            if (fails > MAX_DIM_POLL_FAILURES) partialDimensionsRef.current.delete(dim);
          }
        })
      );
    }, DIMENSION_POLL_MS);
  }

  function startPolling(jobId) {
    stopPolling();
    let dimPollingStarted = false;
    pollRef.current = setInterval(async () => {
      try {
        const updated = await getEvaluation(jobId);
        setJob((prev) => ({ ...updated, repo: prev?.repo }));
        // Use dimensions list from job (emitted during setup phase)
        if (updated.dimensions?.length && !requestedDimensionsRef.current.length) {
          requestedDimensionsRef.current = updated.dimensions;
        }
        // When a dimension enters analyzing phase, start polling it
        if (updated.phase === 'analyzing' && updated.currentDimension) {
          partialDimensionsRef.current.add(updated.currentDimension);
        }
        const hasOutput = updated.outputProject && updated.outputRunId;
        const canPollDims = hasOutput && (updated.phase === 'analyzing' || updated.phase === 'scoring' || updated.status !== 'running');
        if (updated.status !== 'running') {
          stopPolling();
          if (canPollDims && !dimPollingStarted) {
            dimPollingStarted = true;
            startDimensionPolling(updated.outputProject, updated.outputRunId);
          }
        } else if (canPollDims && !dimPollingStarted) {
          dimPollingStarted = true;
          startDimensionPolling(updated.outputProject, updated.outputRunId);
        }
      } catch (err) {
        // Job no longer tracked (e.g. server restarted) — mark as lost
        setJob((prev) => prev ? { ...prev, status: 'lost' } : prev);
        setJobError(err.message);
        stopPolling();
        stopDimensionPolling();
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
    try {
      const created = await startEvaluation(payload);
      setJob({ ...created, repo: payload.repo });
      startPolling(created.jobId);
    } catch (err) {
      setJobError(err.message);
    }
  }

  function clearJob() {
    stopPolling();
    stopDimensionPolling();
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
