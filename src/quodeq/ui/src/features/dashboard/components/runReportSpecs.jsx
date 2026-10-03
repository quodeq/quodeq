import { useCallback, useMemo, useRef } from 'react';
import { useRegisterWindowSpec } from '../../side-pane/index.js';
import { buildRunReport } from '../../../utils/reportBuilder.js';
import { buildDimensionPlanFromViolations } from '../../../utils/explorerUtils.js';
import { formatRunId } from '../../../utils/formatters.js';
import { t } from '../../../strings/index.js';
import { HydratedReportContent } from './HydratedReportContent.jsx';

// Named .jsx (not the brief's .js) since both specs' `render` needs real JSX
// -- Vite/esbuild only auto-enables JSX parsing for .jsx files, not .js.

const filenameLabelFor = (label) => label.replace(/[^a-z0-9-]+/gi, '-').toLowerCase();

/**
 * One pane spec whose body hydrates the deferred detail before building:
 * `render` mounts HydratedReportContent, which leaves its Markdown in a ref
 * that copy/download read; before the pane has rendered once they fall
 * back to a build without detail rather than blocking.
 */
function hydratedSpec({ id, type, title, filename, dimensions, severities, build, markdownRef }) {
  const fallback = () => markdownRef.current ?? build(dimensions);
  return {
    id,
    type,
    title,
    render: () => <HydratedReportContent dimensions={dimensions} severities={severities} build={build} markdownRef={markdownRef} />,
    copy: fallback,
    download: () => ({ filename, body: fallback() }),
  };
}

/**
 * Registers the run page's report and fix plan panes. *dashboard* is the
 * overview payload with the run's finding lists merged in
 * (runViewData.js); until those load, the fix plan has nothing to print and
 * stays unregistered.
 */
export function useRunReportSpecs({ dashboard, runSummary, selectedRunId, projectName, headline = null, since = null }) {
  const runId = dashboard?.selectedRun?.runId || selectedRunId || 'current';
  const dateLabel = dashboard?.selectedRun?.dateLabel || formatRunId(selectedRunId) || 'run';
  const dimensions = dashboard?.dimensions;
  const reportRef = useRef(null);
  const planRef = useRef(null);

  const buildReport = useCallback(
    (dims) => buildRunReport({ dashboard: { ...dashboard, dimensions: dims }, runSummary, projectName, headline, since }),
    [dashboard, runSummary, projectName, headline, since],
  );
  const reportSpec = useMemo(() => {
    if (!dimensions) return null;
    return hydratedSpec({
      id: `report:run:${runId}`, type: 'report', title: t('overview.reportTitle', { name: dateLabel }),
      filename: `run-${filenameLabelFor(dateLabel || runId)}-report.md`,
      dimensions, build: buildReport, markdownRef: reportRef,
    });
  }, [dimensions, runId, dateLabel, buildReport]);
  useRegisterWindowSpec('report', reportSpec);

  const buildPlan = useCallback((dims) => {
    const allViolations = dims.flatMap((d) => (d.violations || []).map((v) => ({ ...v, dimension: d.dimension })));
    return buildDimensionPlanFromViolations(dateLabel, allViolations);
  }, [dateLabel]);
  const fixPlanSpec = useMemo(() => {
    const hasViolations = (dimensions || []).some((d) => (d.violations?.length || 0) > 0);
    if (!hasViolations) return null;
    return hydratedSpec({
      id: `fixplan:run:${runId}`, type: 'fixplan', title: t('overview.fixPlanTitle', { name: dateLabel }),
      filename: `run-${filenameLabelFor(dateLabel || runId)}-fix-plan.md`,
      dimensions, severities: null, build: buildPlan, markdownRef: planRef,
    });
  }, [dimensions, runId, dateLabel, buildPlan]);
  useRegisterWindowSpec('fixplan', fixPlanSpec);
}
