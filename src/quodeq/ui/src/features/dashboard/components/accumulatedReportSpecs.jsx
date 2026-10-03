import { useMemo, useRef } from 'react';
import { useRegisterWindowSpec } from '../../side-pane/index.js';
import { buildOverviewReport } from '../../../utils/reportBuilder.js';
import { OverviewReportContent } from './OverviewReportContent.jsx';
import { t } from '../../../strings/index.js';

// Sibling to runReportSpecs.jsx's useRunReportSpecs -- same
// report-spec-registration pattern, accumulated-overview variant. Named
// .jsx (not .js) for the same reason as runReportSpecs.jsx: `render` needs
// real JSX (<ReportContent/>).
function reportProjectNameFor(data) {
  return data.projectInfo?.displayName
    || data.projectInfo?.name
    || data.selectedDisplayName
    || data.selectedProject
    || 'project';
}

// Returns reportProjectName so the caller can reuse it (AccumulatedOverviewPanel's
// onCardNavigate needs the same value) without recomputing it.
export function useAccumulatedReportSpec({ data, filteredAccumulated, filteredDimensions, headline = null, since = null }) {
  const reportProjectName = reportProjectNameFor(data);
  const hasReportData = Boolean(
    filteredAccumulated?.summary
    && Number.isFinite(parseFloat(filteredAccumulated.summary.numericAverage))
    && (filteredDimensions?.length ?? 0) > 0
  );
  // The rendered body hydrates the printed violations (/scores defers their
  // reason and snippet) and leaves its Markdown here for copy/download;
  // before the pane has rendered once, those fall back to a build without
  // detail rather than blocking.
  const markdownRef = useRef(null);
  const reportSpec = useMemo(() => {
    if (!hasReportData) return null;
    const extras = { headline, since, commitSha: data.selectedRun?.commitSha };
    const buildMarkdown = () => markdownRef.current ?? buildOverviewReport(filteredAccumulated, filteredDimensions || [], reportProjectName, extras);
    return {
      id: `report:overview:${reportProjectName}`,
      type: 'report',
      title: t('overview.reportTitle', { name: reportProjectName }),
      render: () => (
        <OverviewReportContent
          accumulated={filteredAccumulated} dimensions={filteredDimensions || []}
          projectName={reportProjectName} extras={extras} markdownRef={markdownRef}
        />
      ),
      copy: () => buildMarkdown(),
      download: () => ({ filename: `code-quality-report-${reportProjectName}.md`, body: buildMarkdown() }),
    };
  }, [hasReportData, reportProjectName, filteredAccumulated, filteredDimensions, headline, since, data.selectedRun?.commitSha]);
  useRegisterWindowSpec('report', reportSpec);

  return reportProjectName;
}
