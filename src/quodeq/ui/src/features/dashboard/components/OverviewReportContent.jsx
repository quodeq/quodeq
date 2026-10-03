import { useCallback } from 'react';
import { buildOverviewReport } from '../../../utils/reportBuilder.js';
import { HydratedReportContent } from './HydratedReportContent.jsx';

export { hydrateReportDimensions } from './HydratedReportContent.jsx';

/**
 * The Overview report's body: the critical and major violations hydrated,
 * the Markdown built and left in *markdownRef* for copy and download.
 */
export function OverviewReportContent({ accumulated, dimensions, projectName, extras, markdownRef }) {
  const build = useCallback(
    (dims) => buildOverviewReport(accumulated, dims, projectName, extras),
    [accumulated, projectName, extras],
  );
  return <HydratedReportContent dimensions={dimensions} build={build} markdownRef={markdownRef} />;
}
