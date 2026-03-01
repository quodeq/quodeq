import { useEffect, useRef, useState } from 'react';
import { startEvaluation, getEvaluation, cancelEvaluation } from '../../../api/index.js';

export function useEvaluation() {
  const [job, setJob] = useState(null);
  const [jobError, setJobError] = useState('');
  const pollRef = useRef(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
      }
    };
  }, []);

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  function startPolling(jobId) {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const updated = await getEvaluation(jobId);
        setJob((prev) => ({ ...updated, repo: prev?.repo }));
        if (updated.status !== 'running') {
          stopPolling();
        }
      } catch (err) {
        setJobError(err.message);
        stopPolling();
      }
    }, 1500);
  }

  async function startEvaluationJob(payload) {
    setJobError('');
    try {
      const created = await startEvaluation(payload);
      setJob({ ...created, repo: payload.repo });
      startPolling(created.jobId);
    } catch (err) {
      setJobError(err.message);
    }
  }

  function clearJob() {
    setJob(null);
    setJobError('');
    stopPolling();
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

  return { job, jobError, startEvaluation: startEvaluationJob, clearJob, cancelEvaluation: cancelEvaluationJob };
}
