/**
 * Risk-matrix weighting: turns a node's raw violations/compliance/severity
 * counts into the (x, y, b) plot point RiskMatrixView positions and sizes a
 * bubble with. Extracted out of useBubbleLayout verbatim.
 */

// A node whose compliance ratio is high has its x/y dampened toward the
// origin -- a mostly-compliant file with a few violations reads as lower
// risk than the same violation count on a file with none.
const COMPLIANCE_DAMPEN = 0.45;
const SEV_WEIGHT_CRITICAL = 100;
const SEV_WEIGHT_MAJOR = 10;
const SEV_WEIGHT_MINOR = 1;

/**
 * @param {{ violations?: number, compliance?: number, severity?: { critical?: number, major?: number, minor?: number } }} node
 * @returns {{ x: number, y: number, b: number }} x = violations axis, y = severity axis, b = bubble-size basis (total findings)
 */
export function riskPoint(node) {
  const total = (node.violations || 0) + (node.compliance || 0);
  const dampen = total > 0 ? 1 - (node.compliance / total) * COMPLIANCE_DAMPEN : 1;
  return {
    x: (node.violations || 0) * dampen,
    y: ((node.severity?.critical || 0) * SEV_WEIGHT_CRITICAL
      + (node.severity?.major || 0) * SEV_WEIGHT_MAJOR
      + (node.severity?.minor || 0) * SEV_WEIGHT_MINOR) * dampen,
    b: total,
  };
}
