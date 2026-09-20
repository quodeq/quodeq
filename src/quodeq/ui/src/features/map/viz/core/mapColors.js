import { t } from '../../../../strings/index.js';

const RATE_HIGH = 0.9;
const RATE_MEDIUM = 0.7;
const RATE_LOW = 0.4;

const SEVERITY_STATE_KEYS = {
  critical: 'map.stateCritical',
  major: 'map.stateMajor',
  minor: 'map.stateMinor',
};

// One entry per colour bucket: the text/fill colour, the cell background and
// the border. severityColor, severityBorderColor and severityCellStyle are
// the same lookup read through different fields, and the compliance entry is
// the no-violations fallback.
const BUCKETS = {
  critical: { color: 'var(--color-sev-critical-text)', background: 'color-mix(in srgb, var(--color-sev-critical-text) 22%, transparent)', borderColor: 'var(--color-sev-critical-border)' },
  major: { color: 'var(--color-sev-major-text)', background: 'color-mix(in srgb, var(--color-sev-major-text) 22%, transparent)', borderColor: 'var(--color-sev-major-border)' },
  minor: { color: 'var(--color-sev-minor-text)', background: 'color-mix(in srgb, var(--color-sev-minor-text) 22%, transparent)', borderColor: 'var(--color-sev-minor-border)' },
  compliance: { color: 'var(--color-compliance)', background: 'color-mix(in srgb, var(--color-compliance) 22%, transparent)', borderColor: 'var(--color-compliance-border)' },
};

// The compliance-rate ladder, best first: a rate at or above the threshold
// takes that bucket, anything below them all is critical.
const RATE_BUCKETS = [
  [RATE_HIGH, BUCKETS.compliance],
  [RATE_MEDIUM, BUCKETS.minor],
  [RATE_LOW, BUCKETS.major],
];

function severityBucket(severity) {
  return BUCKETS[severity] || BUCKETS.compliance;
}

function rateBucket(rate) {
  for (const [min, bucket] of RATE_BUCKETS) {
    if (rate >= min) return bucket;
  }
  return BUCKETS.critical;
}

export function severityColor(severity) {
  return severityBucket(severity).color;
}

export function complianceRateColor(rate) {
  return rateBucket(rate).color;
}

export function severityCellStyle(sev) {
  return BUCKETS[sev] || null;
}

export function complianceRateCellStyle(rate) {
  return rateBucket(rate);
}

export function healthColor(complianceRate) {
  return complianceRateColor(complianceRate);
}

export function worstSeverity(severity) {
  if (!severity) return null;
  if (severity.critical > 0) return 'critical';
  if (severity.major > 0) return 'major';
  if (severity.minor > 0) return 'minor';
  return null;
}

function severityBorderColor(severity) {
  return severityBucket(severity).borderColor;
}

function complianceRateBorderColor(rate) {
  return rateBucket(rate).borderColor;
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

/**
 * The screen-reader equivalent of the colour nodeColor picks for this node:
 * the worst severity word in violations mode, the rounded compliance
 * percentage in the compliance/health modes. Colour is the only cue a
 * sighted user gets, so every focusable node label carries this too.
 */
export function nodeStateText(node, viewMode) {
  if (viewMode === 'compliance' || viewMode === 'health') {
    return t('map.stateCompliance', { pct: Math.round((node.complianceRate || 0) * 100) });
  }
  const worst = worstSeverity(node.severity || {});
  return worst ? t(SEVERITY_STATE_KEYS[worst]) : t('map.stateClean');
}

export function nodeSize(node, viewMode) {
  switch (viewMode) {
    case 'violations': return node.violations || 1;
    case 'compliance': return node.compliance || 1;
    case 'health': return (node.violations + node.compliance) || 1;
    default: return node.violations || 1;
  }
}
