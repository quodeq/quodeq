import { useEffect, useRef, useState } from 'react';
import { startEvaluation, getEvaluation, cancelEvaluation, getDimensionEval, listEvaluations } from '../../../api/index.js';

export function useEvaluation() {
  const [job, setJob] = useState(null);
  const [jobError, setJobError] = useState('');
  const [liveViolations, setLiveViolations] = useState({});

  const pollRef = useRef(null);
  const dimPollRef = useRef(null);
  const requestedDimensionsRef = useRef([]);
  const liveViolationsRef = useRef({});
  const partialDimensionsRef = useRef(new Set());

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
    dimPollRef.current = setInterval(async () => {
      const dims = requestedDimensionsRef.current;
      if (!dims.length) {
        stopDimensionPolling();
        return;
      }

      const pending = dims.filter(d => !liveViolationsRef.current[d] || partialDimensionsRef.current.has(d));
      if (!pending.length) {
        stopDimensionPolling();
        return;
      }

      await Promise.allSettled(
        pending.map(async (dim) => {
          try {
            const data = await getDimensionEval(project, runId, dim);
            if (data?.violations) {
              if (data.partial) {
                partialDimensionsRef.current.add(dim);
              } else {
                partialDimensionsRef.current.delete(dim);
              }
              setLiveViolations(prev => ({ ...prev, [dim]: data.violations }));
            }
          } catch {
            // dimension not ready yet — silently skip
          }
        })
      );
    }, 2000);
  }

  function startPolling(jobId) {
    stopPolling();
    let dimPollingStarted = false;
    pollRef.current = setInterval(async () => {
      try {
        const updated = await getEvaluation(jobId);
        setJob((prev) => ({ ...updated, repo: prev?.repo }));
        if (updated.status !== 'running') {
          stopPolling();
          // one final dimension sweep after job completes
          if (updated.outputProject && updated.outputRunId && !dimPollingStarted) {
            dimPollingStarted = true;
            startDimensionPolling(updated.outputProject, updated.outputRunId);
          }
        } else if (updated.outputProject && updated.outputRunId && !dimPollingStarted) {
          dimPollingStarted = true;
          startDimensionPolling(updated.outputProject, updated.outputRunId);
        }
      } catch (err) {
        setJobError(err.message);
        stopPolling();
        stopDimensionPolling();
      }
    }, 1500);
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
