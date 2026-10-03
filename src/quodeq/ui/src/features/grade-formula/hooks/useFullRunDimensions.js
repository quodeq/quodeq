import { hasBodies } from '../../../models/dimension.js';
import { useRunFindings } from '../../dashboard/hooks/useRunFindings.js';

/**
 * The run's dimensions with bodies. The dashboard is the overview shape
 * (counts only), so the TYPES tab (which counts `violations[].req`) reads
 * the run's findings through the same query the run page and the Explorer
 * use; a visited run page has already warmed it.
 *
 * @returns {Array} the given dimensions when full, else the run findings'
 *   dimensions, else [] while loading
 */
export function useFullRunDimensions({ project, runId, source, dimensions }) {
  const slim = !hasBodies(dimensions);
  const findings = useRunFindings({ project, runId, source, enabled: slim });
  return slim ? findings.dimensions : dimensions;
}
