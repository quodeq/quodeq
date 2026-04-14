const RATE_HIGH = 0.9;
const RATE_MEDIUM = 0.7;
const RATE_LOW = 0.4;

export function severityColor(severity) {
  switch (severity) {
    case 'critical': return 'var(--color-sev-critical-text)';
    case 'major': return 'var(--color-sev-major-text)';
    case 'minor': return 'var(--color-sev-minor-text)';
    default: return 'var(--color-compliance)';
  }
}

export function complianceRateColor(rate) {
  if (rate >= RATE_HIGH) return 'var(--color-compliance)';
  if (rate >= RATE_MEDIUM) return 'var(--color-sev-minor-text)';
  if (rate >= RATE_LOW) return 'var(--color-sev-major-text)';
  return 'var(--color-sev-critical-text)';
}

const SEV_STYLES = {
  critical: { color: 'var(--color-sev-critical-text)', background: 'color-mix(in srgb, var(--color-sev-critical-text) 22%, transparent)', borderColor: 'var(--color-sev-critical-border)' },
  major: { color: 'var(--color-sev-major-text)', background: 'color-mix(in srgb, var(--color-sev-major-text) 22%, transparent)', borderColor: 'var(--color-sev-major-border)' },
  minor: { color: 'var(--color-sev-minor-text)', background: 'color-mix(in srgb, var(--color-sev-minor-text) 22%, transparent)', borderColor: 'var(--color-sev-minor-border)' },
  compliance: { color: 'var(--color-compliance)', background: 'color-mix(in srgb, var(--color-compliance) 22%, transparent)', borderColor: 'var(--color-compliance-border)' },
};

export function severityCellStyle(sev) {
  return SEV_STYLES[sev] || null;
}

export function complianceRateCellStyle(rate) {
  if (rate >= RATE_HIGH) return SEV_STYLES.compliance;
  if (rate >= RATE_MEDIUM) return SEV_STYLES.minor;
  if (rate >= RATE_LOW) return SEV_STYLES.major;
  return SEV_STYLES.critical;
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

function severityBorderColor(severity) {
  switch (severity) {
    case 'critical': return 'var(--color-sev-critical-border)';
    case 'major': return 'var(--color-sev-major-border)';
    case 'minor': return 'var(--color-sev-minor-border)';
    default: return 'var(--color-compliance-border)';
  }
}

function complianceRateBorderColor(rate) {
  if (rate >= RATE_HIGH) return 'var(--color-compliance-border)';
  if (rate >= RATE_MEDIUM) return 'var(--color-sev-minor-border)';
  if (rate >= RATE_LOW) return 'var(--color-sev-major-border)';
  return 'var(--color-sev-critical-border)';
}

export function nodeBorderColor(node, viewMode) {
  switch (viewMode) {
    case 'violations': return severityBorderColor(worstSeverity(node.severity));
    case 'compliance': return complianceRateBorderColor(node.complianceRate);
    case 'health': return complianceRateBorderColor(node.complianceRate);
    default: return severityBorderColor(worstSeverity(node.severity));
  }
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
