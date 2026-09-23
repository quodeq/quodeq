// Display labels for enum-ish values that arrive as data (severity levels,
// granularities). Known values render through the catalog; unknown values
// fall back to the raw string rather than a "severity.xyz" key.
import { t } from './index.js';
import { JOB_STATUS } from '../vocab/jobStatus.js';
import { SCOPE_GATE_RULE } from '../vocab/scopeGateRule.js';
import { KNOWN_SEVERITIES } from '../utils/constants.js';
import { GRANULARITY } from '../utils/granularity.js';

const KNOWN_SEVERITY_KEYS = new Set(KNOWN_SEVERITIES);

export function severityLabel(severity) {
  const key = severity || 'unknown';
  return KNOWN_SEVERITY_KEYS.has(key) ? t(`severity.${key}`) : key;
}

const KNOWN_GRANULARITIES = new Set(Object.values(GRANULARITY));

export function granularityLabel(granularity) {
  return KNOWN_GRANULARITIES.has(granularity) ? t(`granularity.${granularity}`) : granularity;
}

const KNOWN_JOB_STATUSES = new Set(Object.values(JOB_STATUS));

export function jobStatusLabel(status) {
  return KNOWN_JOB_STATUSES.has(status) ? t(`status.${status}`) : status;
}

// The scope gate stamps one of these rule names into a finding's
// scopeDowngrade marker. An unrecognized value falls through to the raw
// string rather than a missing-key placeholder, the same fallback every other
// helper here uses for data that did not come from a hardcoded set.
const KNOWN_SCOPE_GATE_RULES = new Set(Object.values(SCOPE_GATE_RULE));

export function scopeGateRuleLabel(rule) {
  return KNOWN_SCOPE_GATE_RULES.has(rule) ? t(`scopeGateRule.${rule}`) : rule;
}
