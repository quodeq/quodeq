import { useEffect, useRef, useState } from 'react';
import { startEvaluation, getEvaluation, cancelEvaluation, getDimensionEval } from '../../../api/index.js';

export function useEvaluation() {
  const [job, setJob] = useState(null);
  const [jobError, setJobError] = useState('');
  const [liveViolations, setLiveViolations] = useState({});

  const pollRef = useRef(null);
  const dimPollRef = useRef(null);
  const requestedDimensionsRef = useRef([]);
  const liveViolationsRef = useRef({});

  useEffect(() => {
    return () => {
      stopPolling();
      stopDimensionPolling();
    };
  }, []);

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

      const pending = dims.filter(d => !liveViolationsRef.current[d]);
      if (!pending.length) {
        stopDimensionPolling();
        return;
      }

      await Promise.allSettled(
        pending.map(async (dim) => {
          try {
            const data = await getDimensionEval(project, runId, dim);
            if (data?.violations) {
              setLiveViolations(prev => {
                const next = { ...prev, [dim]: data.violations };
                liveViolationsRef.current = next;
                return next;
              });
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
            startDimensionPolling(updated.outputProject, updated.outputRunId);
          }
        } else if (updated.outputProject && updated.outputRunId && !dimPollingStarted) {
          dimPollingStarted = true;
          startDimensionPolling(updated.outputProject, updated.outputRunId);
        }
      } catch (err) {
        setJobError(err.message);
        stopPolling();
      }
    }, 1500);
  }

  async function startEvaluationJob(payload) {
    setJobError('');
    requestedDimensionsRef.current = payload.dimensions ?? [];
    liveViolationsRef.current = {};
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
