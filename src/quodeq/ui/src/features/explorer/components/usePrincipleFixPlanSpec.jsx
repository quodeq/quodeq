import { useMemo } from 'react';
import { buildPrinciplePlanText } from '../../../utils/planTextBuilders.js';
import { SEVERITY_ORDER as EVAL_SEVERITY_ORDER } from '../../../utils/formatters.js';
import { useRegisterWindowSpec, ReportContent } from '../../side-pane/index.js';
import { filterTitleSuffix } from './usePrincipleReportSpec.jsx';

/** Registers the principle's fix-plan side-pane window spec, kept in sync
 * with the active severity filter. */
export function usePrincipleFixPlanSpec({
  principle, dimension, runId, filteredViolations, principleData, activeSevFilter,
}) {
  const fixPlanSpec = useMemo(() => {
    if (!principle || filteredViolations.length === 0) return null;
    const buildBySeverity = () => {
      const bucket = {};
      for (const sev of EVAL_SEVERITY_ORDER) {
        bucket[sev] = filteredViolations.filter((v) => (v.severity || 'minor').toLowerCase() === sev);
      }
      return bucket;
    };
    const buildMarkdown = () => buildPrinciplePlanText(
      principle,
      filteredViolations,
      buildBySeverity(),
      principleData,
      activeSevFilter,
    );
    const slug = `${(dimension || 'dim')}-${principle}`.replace(/[^a-z0-9-]+/gi, '-').toLowerCase();
    return {
      id: `fixplan:principle:${dimension || 'dim'}:${principle}:${runId || 'current'}`,
      type: 'fixplan',
      title: `${principle} fix plan${filterTitleSuffix(activeSevFilter)}`,
      render: () => <ReportContent markdown={buildMarkdown()} />,
      copy: () => buildMarkdown(),
      download: () => ({ filename: `principle-${slug}-fix-plan.md`, body: buildMarkdown() }),
    };
  }, [principle, dimension, runId, filteredViolations, principleData, activeSevFilter]);
  useRegisterWindowSpec('fixplan', fixPlanSpec);
}
