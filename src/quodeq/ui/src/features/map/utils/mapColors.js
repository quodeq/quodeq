export function severityColor(severity) {
  switch (severity) {
    case 'critical': return 'var(--map-critical)';
    case 'major': return 'var(--map-major)';
    case 'minor': return 'var(--map-minor)';
    default: return 'var(--map-clean)';
  }
}

export function complianceRateColor(rate) {
  if (rate >= 0.9) return 'var(--map-clean)';
  if (rate >= 0.7) return 'var(--map-minor)';
  if (rate >= 0.4) return 'var(--map-major)';
  return 'var(--map-critical)';
}

export function healthColor(complianceRate) {
  return complianceRateColor(complianceRate);
}

export function worstSeverity(severity) {
  if (severity.critical > 0) return 'critical';
  if (severity.major > 0) return 'major';
  if (severity.minor > 0) return 'minor';
  return null;
}

export function nodeColor(node, viewMode) {
  switch (viewMode) {
    case 'violations': return severityColor(worstSeverity(node.severity));
    case 'compliance': return complianceRateColor(node.complianceRate);
    case 'health': return healthColor(node.complianceRate);
    default: return severityColor(worstSeverity(node.severity));
  }
}

export function nodeSize(node, viewMode) {
  switch (viewMode) {
    case 'violations': return node.violations || 1;
    case 'compliance': return node.compliance || 1;
    case 'health': return (node.violations + node.compliance) || 1;
    default: return node.violations || 1;
  }
}
