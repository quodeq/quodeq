import { useMemo } from 'react';
import { buildPrincipleReport } from '../../../utils/reportBuilder.js';
import { useRegisterWindowSpec, ReportContent } from '../../side-pane/index.js';

function filterTitleSuffix(filter) {
  if (!filter || filter === 'all') return '';
  return ` (${filter})`;
}

/** Registers the principle's report side-pane window spec, kept in sync
 * with the active severity filter and live (post-dismiss) score/grade. */
export function usePrincipleReportSpec({
  principle, dimension, runId, score, grade, liveScore, liveGrade,
  filteredViolations, compliance, principleData, activeSevFilter,
}) {
  const reportSpec = useMemo(() => {
    if (!principle) return null;
    const buildMarkdown = () => buildPrincipleReport({
      principle, dimension,
      score: liveScore ?? score, grade: liveGrade ?? grade,
      violations: filteredViolations,
      compliance, principleData, runId,
      severityFilter: activeSevFilter,
    });
    const slug = `${(dimension || 'dim')}-${principle}`.replace(/[^a-z0-9-]+/gi, '-').toLowerCase();
    return {
      id: `report:principle:${dimension || 'dim'}:${principle}:${runId || 'current'}`,
      type: 'report',
      title: `${principle} report${filterTitleSuffix(activeSevFilter)}`,
      render: () => <ReportContent markdown={buildMarkdown()} />,
      copy: () => buildMarkdown(),
      download: () => ({ filename: `principle-${slug}-report.md`, body: buildMarkdown() }),
    };
  }, [principle, dimension, runId, score, grade, liveScore, liveGrade, filteredViolations, compliance, principleData, activeSevFilter]);
  useRegisterWindowSpec('report', reportSpec);
}

export { filterTitleSuffix };
