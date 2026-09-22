import { useMemo } from 'react';
import { useRegisterWindowSpec, ReportContent } from '../../side-pane/index.js';
import { buildRunReport } from '../../../utils/reportBuilder.js';
import { buildDimensionPlanFromViolations } from '../../../utils/explorerUtils.js';
import { formatRunId } from '../../../utils/formatters.js';
import { t } from '../../../strings/index.js';

// Named .jsx (not the brief's .js) since both specs' `render` needs real JSX
// (<ReportContent/>) -- Vite/esbuild only auto-enables JSX parsing for .jsx
// files, not .js.
export function useRunReportSpecs({ dashboard, runSummary, selectedRunId, projectName }) {
  const reportSpec = useMemo(() => {
    if (!dashboard?.dimensions) return null;
    const runId = dashboard?.selectedRun?.runId || selectedRunId || 'current';
    const dateLabel = dashboard?.selectedRun?.dateLabel || formatRunId(selectedRunId) || 'run';
    const buildMarkdown = () => buildRunReport({ dashboard, runSummary, projectName });
    const filenameLabel = (dateLabel || runId).replace(/[^a-z0-9-]+/gi, '-').toLowerCase();
    return {
      id: `report:run:${runId}`,
      type: 'report',
      title: t('overview.reportTitle', { name: dateLabel }),
      render: () => <ReportContent markdown={buildMarkdown()} />,
      copy: () => buildMarkdown(),
      download: () => ({ filename: `run-${filenameLabel}-report.md`, body: buildMarkdown() }),
    };
  }, [dashboard, runSummary, selectedRunId, projectName]);
  useRegisterWindowSpec('report', reportSpec);

  const fixPlanSpec = useMemo(() => {
    const dims = dashboard?.dimensions || [];
    const hasViolations = dims.some((d) => (d.violations?.length || 0) > 0);
    if (!hasViolations) return null;
    const runId = dashboard?.selectedRun?.runId || selectedRunId || 'current';
    const dateLabel = dashboard?.selectedRun?.dateLabel || formatRunId(selectedRunId) || 'run';
    const filenameLabel = (dateLabel || runId).replace(/[^a-z0-9-]+/gi, '-').toLowerCase();
    const buildMarkdown = () => {
      const allViolations = dims.flatMap((d) => (d.violations || []).map((v) => ({ ...v, dimension: d.dimension })));
      return buildDimensionPlanFromViolations(dateLabel, allViolations);
    };
    return {
      id: `fixplan:run:${runId}`,
      type: 'fixplan',
      title: t('overview.fixPlanTitle', { name: dateLabel }),
      render: () => <ReportContent markdown={buildMarkdown()} />,
      copy: () => buildMarkdown(),
      download: () => ({ filename: `run-${filenameLabel}-fix-plan.md`, body: buildMarkdown() }),
    };
  }, [dashboard, selectedRunId]);
  useRegisterWindowSpec('fixplan', fixPlanSpec);
}
