import { useEffect, useMemo } from 'react';
import { ReportContent } from '../../side-pane/index.js';
import { useHydratedFindings } from '../../explorer/hooks/useHydratedCompliance.js';
import { FINDING_TYPE } from '../../../vocab/findingType.js';
import { SEVERITY } from '../../../vocab/severity.js';

/**
 * The severities the scored reports print with reason and snippet
 * (utils/reportBuilder/dimensionSummary.js); /scores defers those fields,
 * so only those rows are hydrated. Fix plans print every row.
 */
export const REPORT_SEVERITIES = new Set([SEVERITY.CRITICAL, SEVERITY.MAJOR]);

const identity = (v) => [v.file, v.line, v.endLine, v.principle, v.title].join('\u0000');

function printedViolations(dimensions, severities) {
  return (dimensions || []).flatMap((dim) => (dim.violations || []).filter((v) => !severities || severities.has(v.severity)));
}

/**
 * The dimensions with each printed violation replaced by its hydrated
 * counterpart (matched by finding identity); other rows and every other
 * field are left as they are.
 * @param {Array} dimensions
 * @param {Array} hydrated
 * @returns {Array}
 */
export function hydrateReportDimensions(dimensions, hydrated) {
  const byIdentity = new Map(hydrated.map((v) => [identity(v), v]));
  return (dimensions || []).map((dim) => ({
    ...dim,
    violations: (dim.violations || []).map((v) => byIdentity.get(identity(v)) ?? v),
  }));
}

/**
 * A report pane body whose Markdown needs the deferred finding detail:
 * hydrates the violations *severities* selects (all when null), hands the
 * hydrated dimensions to *build*, keeps the Markdown in *markdownRef* for the
 * pane's copy and download actions, and renders it.
 * @param {{dimensions: Array, severities?: Set|null, build: (dims: Array) => string, markdownRef?: {current: string|null}}} props
 */
export function HydratedReportContent({ dimensions, severities = REPORT_SEVERITIES, build, markdownRef }) {
  const printed = useMemo(() => printedViolations(dimensions, severities), [dimensions, severities]);
  const hydrated = useHydratedFindings(printed, FINDING_TYPE.VIOLATION);
  const markdown = useMemo(() => build(hydrateReportDimensions(dimensions, hydrated)), [build, dimensions, hydrated]);
  useEffect(() => {
    if (markdownRef) markdownRef.current = markdown;
  }, [markdown, markdownRef]);
  return <ReportContent markdown={markdown} />;
}
