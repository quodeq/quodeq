import { t } from '../../../../strings/index.js';
import { PERCENT } from '../../../../constants.js';

// Most severe first, so every panel reads the same. Labels are resolved per
// build, not here, so a locale change is picked up.
const SEVERITY_LINES = [
  { key: 'critical', labelKey: 'map.critical', color: 'var(--color-sev-critical-text)' },
  { key: 'major', labelKey: 'map.major', color: 'var(--color-sev-major-text)' },
  { key: 'minor', labelKey: 'map.minor', color: 'var(--color-sev-minor-text)' },
];

/**
 * One panel line per non-zero severity. Folder views tint their lines with
 * the severity tokens; a zoomed file leaves them plain.
 */
export function severityLines(counts, { colored }) {
  const sev = counts || {};
  return SEVERITY_LINES
    .filter(({ key }) => sev[key] > 0)
    .map(({ key, labelKey, color }) => {
      const label = t(labelKey);
      return colored ? { label, value: sev[key], color } : { label, value: sev[key] };
    });
}

/** Whole-percent compliance, or a dash when the rate is unknown. */
function complianceValue(rate) {
  return rate == null ? '—' : (rate * PERCENT).toFixed(0) + '%';
}

/**
 * The folder-level panel lines shared by the galaxy and the pack views:
 * compliance, contents, violations, then the coloured severity breakdown
 * when there is anything to break down.
 */
export function folderLines({ complianceRate, contents, violations, severity }) {
  const lines = [
    { label: t('map.compliance'), value: complianceValue(complianceRate) },
    { label: t('map.contents'), value: contents },
    { label: t('map.violations'), value: violations },
  ];
  if (violations > 0) lines.push(...severityLines(severity, { colored: true }));
  return lines;
}
