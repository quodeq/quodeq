import { Router } from 'express';
import { listProjects, buildDashboard, buildAccumulatedData } from '../parsers/reportParser.js';
import { parseEvalFile } from '../parsers/evalParser.js';

export function createProjectsRouter({ reportsRoot }) {
  const router = Router();

  router.get('/projects', (_req, res) => {
    const projects = listProjects(reportsRoot);
    res.json({ projects });
  });

  router.get('/projects/:project/dashboard', (req, res) => {
    try {
      const run = req.query.run ? String(req.query.run) : 'latest';
      const dashboard = buildDashboard(reportsRoot, req.params.project, run);
      res.json(dashboard);
    } catch (error) {
      res.status(404).json({ error: error.message });
    }
  });

  router.get('/projects/:project/accumulated', (req, res) => {
    const { project } = req.params;
    const { asOf } = req.query;
    const data = buildAccumulatedData(reportsRoot, project, asOf || null);
    if (!data) {
      return res.status(404).json({ error: 'Project not found' });
    }
    res.json(data);
  });

  router.get('/projects/:project/runs/:runId/dimensions/:dimension/eval', (req, res) => {
    const { project, runId, dimension } = req.params;
    const data = parseEvalFile(reportsRoot, project, runId, dimension);
    if (!data) {
      return res.status(404).json({ error: 'Eval file not found' });
    }
    res.json(data);
  });

  router.get('/projects/:project/runs/:runId/violations', (req, res) => {
    const { project, runId } = req.params;

    try {
      const dashboard = buildDashboard(reportsRoot, project, runId);

      const summary = {
        total: 0,
        critical: 0,
        major: 0,
        minor: 0,
        byFile: {}
      };

      for (const dim of dashboard.dimensions || []) {
        summary.total += dim.totals?.violationCount || 0;
        summary.critical += dim.totals?.severity?.critical || 0;
        summary.major += dim.totals?.severity?.major || 0;
        summary.minor += dim.totals?.severity?.minor || 0;

        for (const violation of dim.violations || []) {
          if (violation.file) {
            if (!summary.byFile[violation.file]) {
              summary.byFile[violation.file] = { path: violation.file, count: 0, critical: 0, major: 0, minor: 0 };
            }
            summary.byFile[violation.file].count += 1;
            if (violation.severity === 'critical') {
              summary.byFile[violation.file].critical += 1;
            } else if (violation.severity === 'major') {
              summary.byFile[violation.file].major += 1;
            } else if (violation.severity === 'minor') {
              summary.byFile[violation.file].minor += 1;
            }
          }
        }
      }

      summary.files = Object.values(summary.byFile)
        .sort((a, b) => b.count - a.count)
        .slice(0, 20);
      delete summary.byFile;

      res.json(summary);
    } catch (error) {
      res.status(404).json({ error: error.message });
    }
  });

  return router;
}
