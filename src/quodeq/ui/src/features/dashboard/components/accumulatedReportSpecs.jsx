import { useMemo } from 'react';
import { useRegisterWindowSpec, ReportContent } from '../../side-pane/index.js';
import { buildOverviewReport } from '../../../utils/reportBuilder.js';
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
export function useAccumulatedReportSpec({ data, filteredAccumulated, filteredDimensions }) {
  const reportProjectName = reportProjectNameFor(data);
  const hasReportData = Boolean(
    filteredAccumulated?.summary
    && Number.isFinite(parseFloat(filteredAccumulated.summary.numericAverage))
    && (filteredDimensions?.length ?? 0) > 0
  );
  const reportSpec = useMemo(() => {
    if (!hasReportData) return null;
    const buildMarkdown = () => buildOverviewReport(filteredAccumulated, filteredDimensions || [], reportProjectName);
    return {
      id: `report:overview:${reportProjectName}`,
      type: 'report',
      title: t('overview.reportTitle', { name: reportProjectName }),
      render: () => <ReportContent markdown={buildMarkdown()} />,
      copy: () => buildMarkdown(),
      download: () => ({ filename: `code-quality-report-${reportProjectName}.md`, body: buildMarkdown() }),
    };
  }, [hasReportData, reportProjectName, filteredAccumulated, filteredDimensions]);
  useRegisterWindowSpec('report', reportSpec);

  return reportProjectName;
}
