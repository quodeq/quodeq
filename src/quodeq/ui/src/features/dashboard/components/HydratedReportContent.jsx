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

function printedViolations(dimensions, severities) {
  return (dimensions || []).flatMap((dim) => (dim.violations || []).filter((v) => !severities || severities.has(v.severity)));
}

/**
 * The dimensions with the printed violations of each replaced by the rows
 * its detail fetch returned (they carry the ref of the dimension they were
 * fetched for); the rows *severities* leaves unprinted, and every other
 * field, stay as they are. A dimension whose detail has not loaded is left
 * alone.
 * @param {Array} dimensions
 * @param {Array} hydrated
 * @param {Set|null} [severities]
 * @returns {Array}
 */
export function hydrateReportDimensions(dimensions, hydrated, severities = null) {
  return (dimensions || []).map((dim) => {
    const rows = hydrated.filter((v) => v.detailRef?.dimension === dim.dimension && !v.detailDeferred);
    if (!rows.length) return dim;
    const unprinted = severities ? (dim.violations || []).filter((v) => !severities.has(v.severity)) : [];
    return { ...dim, violations: [...rows, ...unprinted] };
  });
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
  const select = useMemo(() => (severities ? (v) => severities.has(v.severity) : undefined), [severities]);
  const hydrated = useHydratedFindings(printed, FINDING_TYPE.VIOLATION, { select });
  const markdown = useMemo(() => build(hydrateReportDimensions(dimensions, hydrated, severities)), [build, dimensions, hydrated, severities]);
  useEffect(() => {
    if (markdownRef) markdownRef.current = markdown;
  }, [markdown, markdownRef]);
  return <ReportContent markdown={markdown} />;
}
