import { Router } from 'express';

export function createEvaluationsRouter({ jobManager }) {
  const router = Router();

  router.post('/evaluations', (req, res) => {
    try {
      const job = jobManager.startJob(req.body ?? {});
      res.status(202).json(job);
    } catch (error) {
      if (error.code === 'INVALID_INPUT') {
        res.status(400).json({ error: error.message });
        return;
      }

      if (error.code === 'JOB_RUNNING') {
        res.status(409).json({ error: error.message });
        return;
      }

      res.status(500).json({ error: error.message });
    }
  });

  router.get('/evaluations/:jobId', (req, res) => {
    const job = jobManager.getJob(req.params.jobId);
    if (!job) {
      res.status(404).json({ error: 'Job not found' });
      return;
    }
    res.json(job);
  });

  router.delete('/evaluations/:jobId', (req, res) => {
    const cancelled = jobManager.cancelJob(req.params.jobId);
    if (!cancelled) {
      res.status(404).json({ error: 'Job not found or not running' });
      return;
    }
    res.json({ ok: true });
  });

  return router;
}
