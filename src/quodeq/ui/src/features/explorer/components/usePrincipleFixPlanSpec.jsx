import { useMemo } from 'react';
import { buildPrinciplePlanText } from '../../../utils/planTextBuilders.js';
import { KNOWN_SEVERITIES } from '../../../utils/constants.js';
import { useRegisterWindowSpec, ReportContent } from '../../side-pane/index.js';
import { filterTitleSuffix } from './usePrincipleReportSpec.jsx';
import { SEVERITY } from '../../../vocab/severity.js';

/** Registers the principle's fix-plan side-pane window spec, kept in sync
 * with the active severity filter. */
export function usePrincipleFixPlanSpec({
  principle, dimension, runId, filteredViolations, principleData, activeSevFilter,
}) {
  const fixPlanSpec = useMemo(() => {
    if (!principle || filteredViolations.length === 0) return null;
    const buildBySeverity = () => {
      const bucket = {};
      for (const sev of KNOWN_SEVERITIES) {
        bucket[sev] = filteredViolations.filter((v) => (v.severity || SEVERITY.MINOR).toLowerCase() === sev);
      }
      return bucket;
    };
    const buildMarkdown = () => buildPrinciplePlanText({
      principle,
      violations: filteredViolations,
      violationsBySeverity: buildBySeverity(),
      principleData,
      severityFilter: activeSevFilter,
    });
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
