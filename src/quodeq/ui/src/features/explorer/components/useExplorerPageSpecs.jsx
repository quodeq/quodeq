import { useCallback, useMemo, useRef } from 'react';
import { buildDimensionPlanFromViolations } from '../../../utils/explorerUtils.js';
import { buildDimensionReport } from '../../../utils/reportBuilder.js';
import { useRegisterWindowSpec } from '../../side-pane/index.js';
import { hydratedReportSpec } from '../../dashboard/components/HydratedReportContent.jsx';
import { t } from '../../../strings/index.js';

/**
 * Registers the dimension's report + fix-plan side-pane window specs, kept
 * in sync with the active run. A finished run's eval defers each finding's
 * reason, snippet and references, so both panes hydrate the rows they print
 * before building (hydratedReportSpec), like the run page's.
 */
export function useExplorerPageSpecs({ evalData, principleGrades, allViolations, overallGrade, activeDateLabel, activeRunId }) {
  const dim = (evalData?.dimension || t('explorer.unknownDimension')).toLowerCase();
  const dimensions = useMemo(
    () => (evalData ? [{ dimension: evalData.dimension, violations: allViolations }] : null),
    [evalData, allViolations],
  );
  const reportRef = useRef(null);
  const planRef = useRef(null);

  const buildReport = useCallback((dims) => buildDimensionReport({
    evalData,
    principleGrades: principleGrades || [],
    allViolations: dims[0]?.violations || [],
    overallGrade,
    dateLabel: activeDateLabel,
    runId: activeRunId,
  }), [evalData, principleGrades, overallGrade, activeDateLabel, activeRunId]);
  const reportSpec = useMemo(() => {
    if (!dimensions) return null;
    return hydratedReportSpec({
      id: `report:dimension:${dim}:${activeRunId ?? 'current'}`, type: 'report',
      title: t('overview.reportTitle', { name: dim }), filename: `${dim}-report.md`,
      dimensions, build: buildReport, markdownRef: reportRef,
    });
  }, [dimensions, dim, activeRunId, buildReport]);
  useRegisterWindowSpec('report', reportSpec);

  const buildPlan = useCallback(
    (dims) => buildDimensionPlanFromViolations(evalData?.dimension, dims[0]?.violations || []),
    [evalData?.dimension],
  );
  const fixPlanSpec = useMemo(() => {
    if (!dimensions || allViolations.length === 0) return null;
    return hydratedReportSpec({
      id: `fixplan:dimension:${dim}:${activeRunId ?? 'current'}`, type: 'fixplan',
      title: t('overview.fixPlanTitle', { name: dim }), filename: `${dim}-fix-plan.md`,
      dimensions, severities: null, build: buildPlan, markdownRef: planRef,
    });
  }, [dimensions, allViolations.length, dim, activeRunId, buildPlan]);
  useRegisterWindowSpec('fixplan', fixPlanSpec);
}
