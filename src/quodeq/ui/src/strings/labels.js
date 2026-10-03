// Display labels for enum-ish values that arrive as data (severity levels,
// granularities). Known values render through the catalog; unknown values
// fall back to the raw string rather than a "severity.xyz" key.
import { t } from './index.js';
import { JOB_STATUS } from '../vocab/jobStatus.js';
import { SCOPE_GATE_RULE } from '../vocab/scopeGateRule.js';
import { KNOWN_SEVERITIES } from '../utils/constants.js';
import { GRANULARITY } from '../utils/granularity.js';

/**
 * A label function for a data value from a known set: a value in `values`
 * renders as the catalog entry `<prefix>.<value>`, anything else passes
 * through as is.
 *
 * @param {string} prefix
 * @param {Iterable<string>} values
 * @returns {(value: string) => string}
 */
export function catalogLabel(prefix, values) {
  const known = new Set(values);
  return (value) => (known.has(value) ? t(`${prefix}.${value}`) : value);
}

const knownSeverityLabel = catalogLabel('severity', KNOWN_SEVERITIES);

export function severityLabel(severity) {
  return knownSeverityLabel(severity || 'unknown');
}

export const granularityLabel = catalogLabel('granularity', Object.values(GRANULARITY));

export const jobStatusLabel = catalogLabel('status', Object.values(JOB_STATUS));

// The scope gate stamps one of these rule names into a finding's
// scopeDowngrade marker. An unrecognized value falls through to the raw
// string rather than a missing-key placeholder, the same fallback every other
// helper here uses for data that did not come from a hardcoded set.
export const scopeGateRuleLabel = catalogLabel('scopeGateRule', Object.values(SCOPE_GATE_RULE));
