// Display labels for enum-ish values that arrive as data (severity levels,
// granularities). Known values render through the catalog; unknown values
// fall back to the raw string rather than a "severity.xyz" key.
import { t } from './index.js';

const KNOWN_SEVERITIES = new Set(['critical', 'major', 'minor', 'unknown']);

export function severityLabel(severity) {
  const key = severity || 'unknown';
  return KNOWN_SEVERITIES.has(key) ? t(`severity.${key}`) : key;
}

const KNOWN_GRANULARITIES = new Set(['day', 'week', 'month']);

export function granularityLabel(granularity) {
  return KNOWN_GRANULARITIES.has(granularity) ? t(`granularity.${granularity}`) : granularity;
}

const KNOWN_JOB_STATUSES = new Set(['running', 'done', 'completed', 'failed', 'cancelled', 'lost']);

export function jobStatusLabel(status) {
  return KNOWN_JOB_STATUSES.has(status) ? t(`status.${status}`) : status;
}
