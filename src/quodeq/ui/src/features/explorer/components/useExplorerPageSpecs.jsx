import { useMemo } from 'react';
import { buildDimensionPlanFromViolations } from '../../../utils/explorerUtils.js';
import { buildDimensionReport } from '../../../utils/reportBuilder.js';
import { useRegisterWindowSpec, ReportContent } from '../../side-pane/index.js';
import { t } from '../../../strings/index.js';

/** Registers the dimension's report + fix-plan side-pane window specs, kept
 * in sync with the active run. */
export function useExplorerPageSpecs({ evalData, principleGrades, allViolations, overallGrade, activeDateLabel, activeRunId }) {
  const reportSpec = useMemo(() => {
    if (!evalData) return null;
    const dim = (evalData.dimension || t('explorer.unknownDimension')).toLowerCase();
    const buildMarkdown = () => buildDimensionReport({
      evalData,
      principleGrades: principleGrades || [],
      allViolations,
      overallGrade,
      dateLabel: activeDateLabel,
      runId: activeRunId,
    });
    return {
      id: `report:dimension:${dim}:${activeRunId ?? 'current'}`,
      type: 'report',
      title: t('overview.reportTitle', { name: dim }),
      render: () => <ReportContent markdown={buildMarkdown()} />,
      copy: () => buildMarkdown(),
      download: () => ({ filename: `${dim}-report.md`, body: buildMarkdown() }),
    };
  }, [evalData, principleGrades, allViolations, overallGrade, activeDateLabel, activeRunId]);
  useRegisterWindowSpec('report', reportSpec);

  const fixPlanSpec = useMemo(() => {
    if (!evalData || allViolations.length === 0) return null;
    const dim = (evalData.dimension || t('explorer.unknownDimension')).toLowerCase();
    const buildMarkdown = () => buildDimensionPlanFromViolations(evalData.dimension, allViolations);
    return {
      id: `fixplan:dimension:${dim}:${activeRunId ?? 'current'}`,
      type: 'fixplan',
      title: t('overview.fixPlanTitle', { name: dim }),
      render: () => <ReportContent markdown={buildMarkdown()} />,
      copy: () => buildMarkdown(),
      download: () => ({ filename: `${dim}-fix-plan.md`, body: buildMarkdown() }),
    };
  }, [evalData, allViolations, activeRunId]);
  useRegisterWindowSpec('fixplan', fixPlanSpec);
}
